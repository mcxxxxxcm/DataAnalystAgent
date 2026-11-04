# Change Recipe：模型视图可重建不变量（M1）——执行剧本

> 给 LLM 的逐步执行清单。每步 = Context + Action + Validation。执行后对着每步 Validation 自检，打 `[x]`。

## Step 1 —— 读约定 / 确认分层
- **Context**: 动手前对齐项目宪法，避免违反分层与安全红线（agreement §1/§3）。
- **Action**: 已读 `openspec/agreement.md`；本 change 属 `middleware/`（可观测捕获）+ `core/`（新增内部能力）+ `config/` + `tests/`，不暴露新工具给 LLM、不触碰 SQL 校验/HITL 边界，无安全红线变更。
- **Validation**: proposal.md 已写明分层归属。`[x]`

## Step 2 —— 新增配置项
- **Context**: agreement §4「配置进 settings 不硬编码」；`recon_model_view_enabled` 作为捕获开关。
- **Action**: 在 `config/settings.py` 的「人工审核/审计」组（`audit_log_enabled` 附近）新增 `recon_model_view_enabled: bool = Field(default=True, ...)`。
- **Validation**: `grep -n recon_model_view_enabled config/settings.py` 存在且带默认值。`[x]`

## Step 3 —— 扩展 ToolCallRecord
- **Context**: `middleware/logging_middleware.py` 的 `ToolCallRecord` 是 JSONL 行结构；需新增 `model_view` 字段承载「模型视图」。
- **Action**: `ToolCallRecord` 增加 `model_view: Optional[str] = None`；`to_json()` 的 `asdict()` 自动带上（无需改序列化逻辑）。`log_tool_call(...)` 增加可选参 `model_view: Optional[str] = None` 并写入 record。
- **Validation**: `py -c "from middleware.logging_middleware import ToolCallRecord; import dataclasses; print([f.name for f in dataclasses.fields(ToolCallRecord)])"` 含 `model_view`。`[x]`

## Step 4 —— 修正 thread_id + 捕获 model_view
- **Context**: 缺口核心：`logging_wrapper.py` 硬编码 `thread_id='current'`、只存原始输出；需取真实会话 id（`request.runtime.config.configurable.thread_id`）并用同阈值 condense 出 `model_view`。
- **Action**: 改 `middleware/logging_wrapper.py`：
  - 从 `request.runtime.config` 解析 thread_id，缺失回退 `'current'`；
  - 计算 `model_view`：`settings.recon_model_view_enabled` 为真时 `model_view = condense_tool_result(str(result), **truncation_settings 同阈值)`（引用 `middleware.truncation` 的 `truncation_settings()`）；
  - `log_tool_call(... thread_id=真实, ..., model_view=model_view)`。
- **Validation**: `py -c "from middleware.logging_wrapper import logging_middleware; print('ok')"` 可导入；`middleware/logging_middleware.py` 的 `ToolCallRecord.to_json` 输出含 `model_view` 键。`[x]`

## Step 5 —— 新增核心重建模块
- **Context**: 重建逻辑是「不暴露给 LLM 的内部能力」，归 `core/`；纯函数、无 DB/LLM。
- **Action**: 新建 `core/recon.py`：
  - `reconstruct_model_messages(events: list[dict]) -> list[BaseMessage]`：按事件类型编排 system→user→assistant_tool_calls→tool_result→resume→summary，tool_result 用 `tool_call_id` 与 assistant_tool_calls 配对；未知类型按既定语义处理。
  - 辅助 `session_events_from_tool_records(records) -> list[dict]`：把含 `model_view`/`tool_name` 的 JSONL 记录转成 tool_result 事件。
- **Validation**: `py -c "from core.recon import reconstruct_model_messages, session_events_from_tool_records; print('ok')"` 可导入。`[x]`

## Step 6 —— 新增测试
- **Context**: 本仓库测试是硬门槛且要求「确定性、无 DB/LLM」回归。
- **Action**: 建 `tests/test_recon.py`，覆盖 proposal「测试计划」7 条：基本轮序、多步配对、忠实性(model_view==condense)、HITL resume、summary、鲁棒性、records→events 消费。测试内 `os.environ.setdefault("API_KEY","test-key-for-unit-test")` 对齐既有 style。
- **Validation**: `pytest tests/test_recon.py -q` 全绿。`[x]`

## Step 7 —— 全量回归 + 评测
- **Context**: 改动带测试是硬门槛；本 change 不触及 schema/安全路径。
- **Action**: 跑 `pytest tests/ -q` 与 `py -m eval.run_eval`。
- **Validation**: `pytest tests/ -q` 全绿；eval 无新增失败（计数不劣化）。`[x]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How/What：重建不变量 + thread_id 修正 + model_view 忠实捕获 + 纯函数 + 测试，全部兑现；**不做**项（API/接 PG）未越界。
- 更新 `README.md`（安全设计或可观测一节说明 tool 日志含 model_view 与真实 thread_id）+ `CHANGELOG.md`（记录「模型视图可重建不变量」）。
- 回填 `openspec/specs/spec.md` 新增 CAP（可观测能力）与 `openspec/tasks.md` 登记 TASK（见 agreement §2.5 DoD 第 4 条）。
- 目录移出 `openspec/changes/` → `openspec/archived/`。
- 提交：中文一句主题，如 `git commit -m "可观测(模型视图不变量)：日志记录真实thread_id与model_view+确定性重建函数"`，附 `Co-Authored-By`。`[x]`