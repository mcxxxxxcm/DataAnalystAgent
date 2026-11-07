# Change Proposal：写操作增强 RETURNING / 批量

> 设计文档。在不放松任何安全红线的前提下，让写操作能回看写入数据，并澄清批量语义。

## 方案

### 现状
- `query_database` 写分支（`tools/sql_tools.py:70`）：`_is_write_dml` 识别 INSERT/UPDATE/DELETE → `run_sql_durable(db_pool.execute, ...)` → `_parse_affected_rows(tag)` → 返回 `{操作, 受影响行数}`。写后 `schema_manager.clear_cache()`，结果**不进** `result_store`。
- 用户提交 `INSERT ... RETURNING id` 时，`RETURNING` 被忽略（execute 只给 tag），回看数据拿不到。

### 目标
- 带 `RETURNING` 的写语句返回**写入后的真实行**（data/columns 回显）。
- 明确多行 `VALUES (...),(...)` 即批量插入语义（文档 + 测试确认无需改 SQL）。
- **不引入**多语句事务（理由见取舍），也不放宽写边界。

### 改动清单
- **修改** `tools/sql_tools.py`：
  - 新增 `_has_returning(sql) -> bool`：`re.search(r'\bRETURNING\b', sql, re.I)`。
  - 写分支改为：
    - 若 `_has_returning(sql)`：走 `run_sql_durable(db_pool.fetch, key=_sql_key, ...)`，`rows=[dict(r) for r in rows]` → `columns=list(rows[0])`，`row_count=len(rows)`。仍 `schema_manager.clear_cache()`、`result_id=""`（不进 store）。返回 `QueryResult(success=True, data, columns, row_count, ...)`。
    - 否则维持 execute + `_parse_affected_rows`。
  - 抽一个纯函数 `_build_write_result(write_type, rows_or_affected)` 便于单测（返回 QueryResult）。
- **返回模型不变**：`QueryResult` 已是 `data/columns/row_count`，无需新增字段 —— RETURING 行直接填 `data`。
- **测试** `tests/test_write_returning.py`（纯逻辑，mock `db_pool.fetch` / `run_sql_durable`）：
  - `_has_returning` 真/假。
  - `_build_write_result`：RETURNING 行 → data/columns/row_count、result_id 为空、success=True。
  - 守卫不放松：RETURNING 分支仍只在 `write_type` 内可达；`enable_sql_write=False` 时 validator 早已拒绝（回归 `test_security`）。
- **文档**：`tools/sql_tools.py` 工具 docstring 与 `README.md` 写操作说明补「RETURNING 回看 / VALUES 多行批量」。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 是否引入多语句事务 | **不做** | 校验器（`sqlparse.split` 多语句检测 + 白名单）拒绝堆叠语句，是防注入安全特性；引入事务需放宽该校验 → 触碰红线 | 不能跨语句原子提交；单语句由 DB 保证原子 |
| RETURNING 结果是否入 result_store | **不入** | 维持 CAP-SEC-008「写结果不适合作图表数据源」；写数据尺寸不可控 | 写回看不能直接 serve 给 create_chart（本就该避免） |
| 批量插入落地方式 | 多行 VALUES 单语句 | 已是合法单语句、无新语义、不突破校验层；即为批量 | 不以「多条独立 INSERT」拼事务实现 |
| RETURNING 是否需新配置开关 | 否 | 跟随既有 `enable_sql_write` 门控，不新增权限面 | 无 |

## 兼容性
- 不带 `RETURNING` 的写行为与现在完全一致（execute + tag 行数）。
- 带 `RETURNING` 的回显数据用既有 `QueryResult` 字段承载，前端/裁剪中间件无需改动。
- 写边界（enable_sql_write / HITL / WHERE 约束）零变化。

## 测试计划
- `tests/test_write_returning.py`：RETURNING 检测、写结果纯函数（回显行/列/行数/result_id 空）、不进 store、写后清缓存（纯函数断言）。
- 回归：`py -m pytest tests/ -q` 全绿。