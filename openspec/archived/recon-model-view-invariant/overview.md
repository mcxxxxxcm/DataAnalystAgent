# Change Overview：模型视图可重建不变量（M1：Model-visible ⟺ logged）

## Why（为什么做）

发给 LLM 的完整消息序列当前**无法从会话日志重建**，违反 DeepSeek Harness 的铁律「Model-visible means logged」：
- 工具日志（`middleware/logging_wrapper.py`）把 `thread_id` **硬编码成 `'current'`**，无法按会话归集；
- 只存原始结果截断 2000 字，**不是**模型真的看到的经 condense 裁剪后的内容，两者不一致；
- 系统提示词 / 用户问题 / 工具结果 / HITL 恢复决策分散在 PG checkpoint 与 JSONL，没有「可由日志重建」这一确定性契约。

结果：做归因、审计、坏 case 分析时，无从证明「我在 log 里看到的内容」就是「模型当时看到的输入」。

## What（做什么 / 不动什么）

要新增/修改：
- 新增 `core/recon.py` —— 确定性重建函数 `reconstruct_model_messages(events)`（纯函数、无 DB/LLM），把声明式会话事件序列编排成 LangChain 消息列表。
- 修改 `middleware/logging_wrapper.py` —— 从 `request.runtime.config.configurable.thread_id` 取真实会话 id（替代硬编码 `'current'`）；捕获 `model_view`（用与送入模型的 condense 相同阈值裁剪）。
- 修改 `middleware/logging_middleware.py` —— `ToolCallRecord` 增加 `model_view` 字段。
- 修改 `config/settings.py` —— 新增 `recon_model_view_enabled`（默认 True，接受度开关）。
- 新增 `tests/test_recon.py` —— 覆盖重建顺序 + 忠实性。

明确**不做**：
- 不加新的 `/api` 端点；不接 PG checkpoint 读取（用户问题/系统提示词入 session 日志留作后续）。
- 不改造 condense 中间件本身、不引入 LLM/DB 依赖。

影响层：`config/`、`core/`（新增内部能力）、`middleware/`（捕获）、`tests/`。

## How（怎么落地，一句概览）

确立「日志 ⟹ 模型视图可重建」这一确定性不变量：用同样的裁剪阈值在工具侧忠实捕获 `model_view`，并用一次纯函数 `reconstruct_model_messages` 把会话事件排回 LangChain 消息序列，配 DB/LLM-free 断言回归。细节步骤见 `recipe.md`。

---

- 关联 issue / 关联模块：DeepSeek Harness「Session log / Model-visible means logged」精髓 → 本项目 `middleware/` 可观测性；关联 backlog 可观测候选 B007。
- 涉及测试：新增 `tests/test_recon.py`；改动 `tests/test_truncation.py`（如适用）。