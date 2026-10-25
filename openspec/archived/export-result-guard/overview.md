# Change Overview：export_result 接入统一 SQL 守卫

## Why（为什么做）

`export_result` 绕过 `guard_query_sql`,用一套并行的旧校验路径,导致它不查系统表黑名单、不走风险三态门禁——这是 proposal §3.3 明示的已知隐患。

## What（做什么 / 不动什么）

- 修改：`tools/analysis_tools.py` —— `export_result` 改用 `guard_query_sql` 替换内联的 `sql_validator.validate` + `sql_sanitizer.sanitize`。
- 新增测试：`tests/test_tool_boundaries.py` —— 断言导出拒绝系统表且未触库。
- **不做**：不动 query_database / 其它工具;不改变导出文件格式与下载接口;不改跨包导入顺序。
- 影响层：tools（安全边界对齐 core/security）。

## How（怎么落地,一句概览）

把 `export_result` 的校验/清理/表名/LIMIT/风险门禁收敛到 `guard_query_sql`,错误与拒绝统一走返回 error 分支,合法查询照常用 `db_pool.fetch`。

---

- 关联 issue / 关联模块：proposal §3.3 已知隐患;`tools/boundaries.py` 的 guard_query_sql
- 涉及测试：`tests/test_tool_boundaries.py`（新增导出守卫用例）