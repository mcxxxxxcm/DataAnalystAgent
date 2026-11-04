# Change Proposal：模型视图可重建不变量（M1）

> 设计文档，给人 review。本 change 落在 **`middleware/`（可观测捕获）+ `core/`（新增内部重建能力，不暴露给 LLM）+ `config/` + `tests/`** 四层，触及 agreement §6 防漂移与 B007 可观测候选，不触碰任何安全红线与现有工具边界。

## 现状 → 目标

**现状（缺口）：**
1. `middleware/logging_wrapper.py:38` `log_tool_call(thread_id='current', ...)` —— thread_id 被写死，日志无法按会话归集/重建。
2. 同文件 `output=str(result)[:2000]` —— 存的是原始 handler 输出的前 2000 字，**不是**模型实际看到的经 `condense_tool_result` 裁剪后的 ToolMessage 内容。
3. `middleware/truncation.py` 的 condense 阈值来自 `settings.tool_result_max_*`（已存在），只要在工具侧用同一阈值裁剪，`model_view` 就与送入模型的 ToolMessage 内容一致。

**目标：**
- 每个工具调用记录真实 `thread_id` + `model_view`（与送入模型同阈值的裁剪内容）。
- 提供一个确定性纯函数 `reconstruct_model_messages(events)`，把「系统提示词 + 用户问题 + 助手工具轮 + 工具结果(model_view) + HITL 恢复决策 + 摘要」编排成 LangChain 消息顺序。
- DB/LLM-free 断言回归：`logged.model_view == condense(logged.output)`，且重建结果 == 期望消息序列。

## 改动清单

- 新建：`core/recon.py` —— `reconstruct_model_messages(events: list[dict]) -> list[BaseMessage]`；辅助 `session_events_from_tool_records(records) -> list[dict]`（把 JSONL 记录转成重建用事件）。纯函数，无 DB/LLM。
  - 事件 schema（声明式，供 tests 与后续作单一数据源）：`{"type":"system"|"user"|"assistant_tool_calls"|"tool_result"|"resume"|"summary", ...}`。顺序契约：
    - `system` → 首个 `SystemMessage`
    - `user` → `HumanMessage`
    - `assistant_tool_calls` → `AIMessage(tool_calls=...)`（带 id，供 tool_result 用 `tool_call_id` 配对）
    - `tool_result` → `ToolMessage`（content 为 `model_view`）
    - `resume` → 来自 `Command(resume={"decisions":[...]})` 的 `HumanMessage`
    - `summary` → `SystemMessage`（长上下文摘要产物）
  - 重建按事件给出顺序，不臆造，单条大胆/缺失报错。
- 修改：`middleware/logging_middleware.py` —— `ToolCallRecord` 增加 `model_view: Optional[str]=None`，`to_json` 一并序列化。
- 修改：`middleware/logging_wrapper.py` —— 从 `request.runtime.config` 解析 thread_id（`config["configurable"]["thread_id"]`，缺失回退 `'current'`）；用 `truncation_settings()` 阈值计算 `model_view = condense_tool_result(str(result))`；传给 `log_tool_call(... model_view=model_view)`。
- 修改：`config/settings.py`（「人工审核/审计」组）—— 新增 `recon_model_view_enabled: bool = Field(default=True, description="是否在工具调用日志记录 model_view（与送入LLM同阈值裁剪的内容），供会话重建/审计")`；`logging_wrapper` 中据此开关捕获。
- 新增：`tests/test_recon.py`。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 忠实性来源 | 工具侧捕获 `model_view`（同阈值 condense） | 与 condense 中间件共用 `truncation_settings()`，天然一致；比事后重算更简单可靠 | 边缘情况：**本轮刚产生的 ToolMessage 送入模型时尚未被跨轮压缩**（condense 是 @before_model 对历史消息生效），首步一瞬时 `model_view` 略早于本轮实际入模内容；影响极小且不破坏「可重建」主契约 |
| 归属层级 | `core/recon.py`（内部能力，不暴露给 LLM） | 符合分层铁律「core/ 不暴露给 LLM」，重建是内部可观测能力 | 非 LLM 工具的职责多一层 |
| thread_id 解析 | 从 `request.runtime.config` 取，缺失回退 'current' | `ToolCallRequest.runtime` 含 `config.configurable.thread_id`（已源码确认）；带兜底保证兼容 | 解析失败时仍回退旧行为 |
| 是否加 API/接 PG | 不加（v1 收口） | 防范围蔓延、保测试 DB-free | 生产接线抛给后续 |
| 配置开关 | `recon_model_view_enabled` 默认 True | 满足「配置进 settings 不硬编码」；量小成本低 | 无 |

## 兼容性

- **向后兼容**：`ToolCallRecord` 新增字段为可选，`to_json` 多序列化一个键，不影响旧读取方（`query_records` 消费其余字段）；`log_tool_call` 新参带默认值。
- thread_id 从 `'current'` 改为真实值——若下游曾按 `'current'` 过滤日志会受影响，但该值本就是占位符、无真实语义，视为修正而非破坏。
- 配置新增默认 True，无行为破坏。

## 测试计划

新增 `tests/test_recon.py`（全 DB/LLM-free）：
1. 基本轮序：system→user→assistant_tool_calls→tool_result→user，断言消息类型与顺序、tool_result 用 `tool_call_id` 配对到对应 AIMessage。
2. 多步工具轮：多轮 tool_result 依次配对、不串位。
3. 忠实性：对一条原始输出，`model_view == condense_tool_result(output, *settings阈值)`。
4. HITL resume：`resume(decisions=[{type:approve}])` 事件 → `HumanMessage`（等价 Command resume）。
5. summary：`summary` 事件 → `SystemMessage`，置于对应位置。
6. 鲁棒性：跳过缺失配对、未知事件类型报错或忽略（选定一个既定语义）。
7. `session_events_from_tool_records`：把含 model_view 的 JSONL 记录（含真实 thread_id）转成重建事件，可被 `reconstruct_model_messages` 消费。

回归：`pytest tests/ -q` 全绿；`py -m eval.run_eval` 不回归（本 change 不触及 schema/安全路径，仅新增可观测层）。