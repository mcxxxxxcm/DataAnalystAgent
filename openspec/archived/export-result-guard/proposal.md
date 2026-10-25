# Change Proposal：export_result 接入统一 SQL 守卫

## 方案

**现状**（`tools/analysis_tools.py:181-222`）：`export_result` 内部各自调用 `sql_validator.validate`(仅 SELECT) + `sql_sanitizer.sanitize`(LIMIT) 后 `db_pool.fetch`。它**缺** query_database 已享受的三项保障：
- 系统表黑名单校验（`is_allowed_table`）
- 风险三态 DENY 门禁（`risk_assessor`）
- 统一错误语义

**目标**：导出与 `query_database` 走同一守卫 `tools.boundaries.guard_query_sql`,消除并行校验路径（对齐 proposal §3.3 与 agreement Avoid#4「不造重复实现」）。

**改动清单**：
- 修改 `tools/analysis_tools.py` —— 函数 `export_result`：
  - 删除内联 `from core.security.sql_validator import sql_validator`、`from core.security.sql_sanitizer import sql_sanitizer` 及其 validate/sanitize 调用。
  - 改为 `from tools.boundaries import guard_query_sql` 后 `final_sql, guard_err = await guard_query_sql(query)`。
  - `if guard_err: return dump_result(ExportResult(success=False, error=guard_err))`
  - 合法时 `rows = await db_pool.fetch(final_sql, timeout=get_settings().sql_timeout)`（不变）。
  - `from tools.boundaries import is_allowed_table` 仍被 analysis_tools 其他函数用到,保持不动。

> 备注：`guard_query_sql` 对 DENY 也会一并把 error 置为拒绝文案（返回值 `(None, error)`）,故统一走 `if guard_err` 分支即可覆盖「校验失败」与「系统表拒绝」与「DENY」三种情况。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 导出守卫来源 | 复用 `guard_query_sql` | 与 query_database 一致,单一安全实现 | 导出不再有独立可调参路径 |
| DENY/CONFIRM 处理 | 仅在 DENY 拒绝,CONFIRM 放行 | 导出为只读 SELECT,行为不比现状更严 | CONFIRM 级导出不额外进 HITL(与现状一致) |
| 系统表导出 | 拒绝 | 对齐查询侧,防读 checkpoint/store 内部表 | 原本可行的内部表导出不再可用(合理) |

## 兼容性

- `export_result` 的公开行为（参数、`file_format`、`download_url`、`file_id`）不变。
- 合法 SELECT 导出仍返回 `success=true`;返回结构 `ExportResult` 不变;前端 `/api/export/{file}` 不受影响。
- 配置项无新增 / 变更;无默认值兼容问题。

## 测试计划

`tests/test_tool_boundaries.py` 新增（沿用无 DB 的 monkeypatch 白名单 + `_run` 模式）：
1. `test_export_result_rejects_system_table_without_db` —— 导出 `SELECT * FROM checkpoints` → 返回 `success=false` 且错误含「不允许的表」;monkeypatch `db_pool.fetch` 为抛错函数,断言未被调用。
2. （可选）`test_export_result_guard_rejects_write_when_disabled` —— 导出 `DELETE FROM sales` → `success=false`。