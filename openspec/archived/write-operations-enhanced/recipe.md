# Change Recipe：写操作增强 RETURNING / 批量（执行剧本）

> 给 LLM 的逐步执行清单。

## Step 1 —— 读约定 + 红线核对
- **Context**: 写操作触碰 CAP-SEC-008 红线，任何放宽都不允许。
- **Action**: 读 `openspec/agreement.md` §3；确认本 change **不放松** enable_sql_write/HITL/WHERE 约束，不引入新权限面。
- **Validation**: 已核红线。 `[ ]`

## Step 2 —— 写分支支持 RETURNING
- **Context**: 写后要能回看数据，但只读边界统一走 `run_sql_durable` 的 fetch/execute 双态。
- **Action**: 在 `tools/sql_tools.py`：
  - 加 `import re`（顶部已有则复用）。
  - 加 `_has_returning(sql) -> bool`。
  - 写分支：`if _has_returning(sql): rows=await run_sql_durable(db_pool.fetch,...); rows=[dict(r) for r in rows]; columns=list(rows[0]) if rows else []` → `QueryResult(success=True, data=rows, row_count=len(rows), columns=columns, execution_time=...)`；仍 `schema_manager.clear_cache()`；`result_id` 留空。else 维持 execute+`_parse_affected_rows`。
  - 抽 `_build_write_result(write_type, rows_or_affected)`：入参为「行列表」或「受影响整数」，内部判型生成 QueryResult（无 RETURNING 的行列表为空 → 走 affected 分支）。
- **Validation**: 写分支逻辑可被单测注入 mock 覆盖；不进 result_store（无 `set_result` 调用）。 `[ ]`

## Step 3 —— 更新工具 docstring
- **Context**: 让 LLM 知道可用 RETURNING / 多行 VALUES 批量。
- **Action**: `query_database` 的 docstring 补：写操作建议 `INSERT ... RETURNING id` 回看；多行 `VALUES (...),(...)` 即批量插入。
- **Validation**: docstring 文字到位。 `[ ]`

## Step 4 —— 测试
- **Context**: 写增强不能破坏红线回归。
- **Action**: 新增 `tests/test_write_returning.py`：
  - `_has_returning` 真/假（含大写/带注释）。
  - `_build_write_result`：行列表 → data/columns/row_count/result_id=''；整数 → affected 分支。
  - 断言「写结果不入 result_store」：验证构建结果 result_id 为空（不依赖真实 store）。
  - 回归：`enable_sql_write=False` 时 `validator.validate("INSERT ... RETURNING id")` 在写未启用即被拒（复用/断言 test_security 语义）。
- **Validation**: `py -m pytest tests/test_write_returning.py tests/test_security.py -q` 通过。 `[ ]`

## Step 5 —— 全量回归
- **Action**: `py -m pytest tests/ -q`。
- **Validation**: 全绿。 `[ ]`

## Final —— 收尾
- 更新 `README.md`（写操作一行说明）、`CHANGELOG.md`。目录移 `openspec/archived/`。中文主题提交。 `[ ]`