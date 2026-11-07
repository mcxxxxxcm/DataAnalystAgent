# Change Overview：写操作增强 RETURNING / 批量（Write Operations Enhanced）

> 让写操作从「只回受影响行数」升级为「可回看写入后的真实数据」，并明确多行 INSERT 即批量；同时诚实收敛「多语句事务」边界为不做。

## Why（为什么做）

写操作（INSERT/UPDATE/DELETE）现在只返回一个受影响行数（`tools/sql_tools.py` 写分支 `_parse_affected_rows`），用户看不到写入后的数据；无「写后回看」，业务价值打折。

## What（做什么 / 不动什么）

- **修改** `tools/sql_tools.py`：写分派识别 `RETURNING` 子句——带 `RETURNING` 的写语句改走 `db_pool.fetch` 抓回返回行，作为 `QueryResult.data/columns` 回显给用户；仍**不进 result_store**（写结果不适合作图表数据源，维持 CAP-SEC-008）。
- **确认批量**：多行 `INSERT INTO t (...) VALUES (...), (...)` 本就是单条合法语句，天然即批量插入，写入说明即可，无需改 SQL。
- **明确不做（取舍记录在案）**：**不引入多语句事务**。因为校验器拒绝堆叠语句（`sqlparse.split` 多语句注入检测 + 白名单），这是安全特性而非缺口；单语句由 DB 原子性保证。不新增配置、不放松任何红线（写仍需 `enable_sql_write` + HITL + DELETE/UPDATE 带 WHERE）。
- **测试** 增改 `tests/test_sql_tools.py`（或新增 `tests/test_write_returning.py`）。

## How（怎么落地，一句概览）

写分支判断 `RETURNING` → 走 fetch 抓回行、清 schema 缓存、不回 store、回显 data；无 `RETURNING` 维持 execute+tag 行数。

---

- 关联模块：`tools/sql_tools.py` · `tools/result_schemas.py`
- 关联 CAP：CAP-SEC-008（写操作边界）· CAP-TOOL-003（返回模型）· TASK-BACKLOG-008
- 涉及测试：`tests/test_write_returning.py`（新增）· `tests/test_security.py`（保持通过）