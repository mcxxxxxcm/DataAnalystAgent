# Change Recipe：写操作支持（INSERT / UPDATE / DELETE）（执行剧本）

> **给 LLM 的逐步执行清单。** 每一步 = `Context(为什么)` + `Action(做什么)` + `Validation(怎么验证通过)`。
> 执行后：对着每步 Validation 自检一遍，在对应步骤后打 `[x]`。

## Step 1 —— 读约定
- **Context**：动手前先对齐项目宪法，这是核心安全相关改动。
- **Action**：读 `openspec/agreement.md`，确认本 change 落在 tools/core 层、不触碰 §3 红线（复用既有校验/HITL/DENY 门禁，不改他们语义方向，只精确化 INSERT 边界）。
- **Validation**：`proposal.md` 已写明分层与兼容性。 `[x]`

## Step 2 —— 修 `risk_assessor.py` INSERT 边界
- **Context**：`NO_WHERE_CLAUSE` 若作用于 INSERT 会把「加数据」误杀成 DENY。
- **Action**：改 `core/security/risk_assessor.py` `_assess()`：无 WHERE 判定限定为 `dml in {'UPDATE','DELETE'}`；同步 `_determine_risk_level` 注释与 recommendations 文案。
- **Validation**：`py -c` 快速验证——`RiskAssessor().assess("INSERT INTO sales(a) VALUES (1)")` 非 CRITICAL；`assess("DELETE FROM sales")` 仍 CRITICAL。 `[ ]`

## Step 3 —— `query_database` 写分派
- **Context**：写操作需执行路径 + 行数返回 + 缓存失效。
- **Action**：改 `tools/sql_tools.py`：加 `_is_write_dml`；`guard_query_sql` 后分派写/SELECT；写走 `db_pool.execute`、解析受影响行数、`schema_manager.clear_cache()`、返回行数且不入 result_store；SELECT 不变。更新 docstring。
- **Validation**：审查 diff 确认 SELECT 路径 `db_pool.fetch`+`set_result` 未变、写路径已加 `clear_cache`。 `[ ]`

## Step 4 —— 提示词写操作引导
- **Context**：LLM 需知道写操作的正确用法与硬边界。
- **Action**：改 `agent/prompts.py`：写操作小节（INSERT 显式列名 / DELETE·UPDATE 必须 WHERE / 会触发人审 / 回述行数；不硬编码表名）。
- **Validation**：更新后系统提示词含「写操作」与「WHERE 限定」语义。 `[ ]`

## Step 5 —— 测试
- **Context**：本仓库测试是硬门槛。
- **Action**：新增 `tests/test_risk_assessor.py`、`tests/test_sql_tools_write.py`；核对 `tests/test_security.py` 既有断言（已核实用 DELETE，不受影响）→ `py -m pytest tests/ -q`。
- **Validation**：全绿，新用例覆盖 INSERT 不误杀 + DELETE/UPDATE 无 WHERE 仍 DENY + 写分派返回行数/清缓存/不入 result_store。 `[ ]`

## Step 6 —— 收尾归档
- **Context**：用户可见变更要落文档，change 归档，提交推送。
- **Action**：更新 `README.md`（核心特性/API 写操作）与 `CHANGELOG.md`（[Unreleased] 写操作条目）；建 OpenSpec 归档（移入 `openspec/archived/`）；`git commit -m "<主题>(<取舍>)：<说明>"` + `Co-Authored-By`；push 远端。
- **Validation**：`git status` 干净、commit 已 push、change 已归档、README/CHANGELOG 已更新。 `[ ]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How 逐条核对：复用入口、返回行数、清缓存、INSERT 边界修复均已兑现。
- `pytest tests/ -q` 全绿已确认。
- 提交已 push 到远端。 `[ ]`