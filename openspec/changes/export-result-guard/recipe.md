# Change Recipe：export_result 接入统一 SQL 守卫（执行剧本）

## Step 1 —— 读约定
- **Context**: 动手前先对齐项目宪法,确认分层与安全红线。
- **Action**: 读取 `openspec/agreement.md`;确认本 change 属 tools 层、触及安全边界(系统表/风险门禁)、不命中 Avoid 陷阱。
- **Validation**: 在 `proposal.md` 标明属于 tools 层并写明安全边界意义。 `[ ]`

## Step 2 —— 改 `export_result`
- **Context**: 把并行校验路径切换为统一守卫 `guard_query_sql`。
- **Action**: 编辑 `tools/analysis_tools.py` 的 `export_result`:
  - 移除内联 `sql_validator` / `sql_sanitizer` 导入与 validate/sanitize 调用。
  - 顶部与 `is_allowed_table` 一起改成 `from tools.boundaries import guard_query_sql, is_allowed_table`。
  - 用 `final_sql, guard_err = await guard_query_sql(query)`;`if guard_err: return dump_result(ExportResult(success=False, error=guard_err))`;后接 `rows = await db_pool.fetch(final_sql, ...)`。
- **Validation**: `grep -n "" tools/analysis_tools.py` 确认无残留 `sql_validator` / `sql_sanitizer` 内联引用,且 `guard_query_sql` 被调用。 `[ ]`

## Step 3 —— 加测试
- **Context**: 安全改动必须带测试且不触真实库。
- **Action**: 在 `tests/test_tool_boundaries.py` 追加 `test_export_result_rejects_system_table_without_db`(monkeypatch `db_pool.fetch` 抛错,断言结果 `success=false` 且未触库)。
- **Validation**: `pytest tests/test_tool_boundaries.py -q` 该新用例通过。 `[ ]`

## Step 4 —— 全量测试
- **Context**: 全量是大门槛。
- **Action**: 项目根目录跑 `pytest tests/ -q`。
- **Validation**: 全绿。 `[ ]`

## Final —— 收尾自检
- 对照 `overview.md` 的 How 逐步核对兑现。
- 无用户可见字段变化 → 不强制改 README;记录性变更可追加 `CHANGELOG.md`。
- 本 change 目录移出 `changes/`(归档或删除)。
- 提交用中文一句主题,如 `git commit -m "重构(tools)：export_result 接入统一 SQL 守卫(<取舍>)：堵住系统表导出绕过"`,附 `Co-Authored-By`。 `[ ]`