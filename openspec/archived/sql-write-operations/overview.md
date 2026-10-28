# Change Overview：写操作支持（INSERT / UPDATE / DELETE）

> 分层：tools 层 + core/security 层（边界判定）+ agent/prompts 层（行为引导）。
> **属于核心安全相关改动**，一处触碰既有安全基线：`risk_assessor` 的「无 WHERE 写 → DENY」判定需精确化到 UPDATE/DELETE，INSERT 除外。不触碰 §3 红线的校验/HITL/任意代码执行默认关等已有门禁，反而复用它们。

## Why（为什么做）

用户需求：**扩展查询能力，支持「添加 / 删除」数据，但要做好边界处理**。
现状 `query_database` 只走 `db_pool.fetch`（SELECT）。写操作虽在 `enable_sql_write` 时可通过校验，但执行路径缺失，且 `risk_assessor` 把「无 WHERE 的写」一律判 CRITICAL→DENY，导致 **INSERT（本就不该有 WHERE）永远被拒**，「加数据」完全不可用。

## What（做什么 / 不动什么）

- **做**：
  1. 修 `core/security/risk_assessor.py`：`NO_WHERE_CLAUSE` 仅适用于 UPDATE / DELETE，INSERT 不误判为危险写。
  2. `tools/sql_tools.py:query_database` 增加写分派：写操作走 `db_pool.execute`，返回受影响行数，写后失效 schema 缓存，不入 result_store；SELECT 路径不变。
  3. `agent/prompts.py` 写操作用法与边界引导（INSERT 显式列名 / DELETE、UPDATE 必须 WHERE / 回述行数）。
  4. `README.md` / `CHANGELOG.md` 同步。
- **不做**：不新建独立 write 工具（复用 query_database）；不做 RETURNING 回传数据（仅返回行数）；不新增配置项（复用 `enable_sql_write`）；不改 HITL 门禁（`query_database` 已在 `tools_requiring_approval`）。
- 影响层：`core/security` / `tools` / `agent` / 文档。

## How（怎么落地,一句概览）

在 `query_database` 内检出写 DML → `db_pool.execute` 取行数 → `schema_manager.clear_cache()` → 返回受影响行数（不入图表缓存）；并先修好 `risk_assessor` 让 INSERT 不再被无 WHERE 误判 DENY。细节见 `recipe.md`。

## 关联模块

- 涉及测试：`tests/test_risk_assessor.py`（新增）、`tests/test_sql_tools_write.py`（新增）、`tests/test_security.py`（核对既有断言不回归；现有 `test_write_without_where_is_critical` 用 DELETE，不受影响）。