# Change Proposal：写操作支持（INSERT / UPDATE / DELETE）

> 设计文档，给**人** review。写清楚方案与取舍，引用真实文件路径。

## 现状 → 目标

**现状**：
- `tools/sql_tools.py:query_database` 一律 `db_pool.fetch`（SELECT 语义），不处理写操作。
- `core/security/risk_assessor.py:126-129` 把「写操作无 WHERE」统一记 `NO_WHERE_CLAUSE` → `_determine_risk_level`（`risk_assessor.py:182`）判 CRITICAL → `guard_query_sql`（`tools/boundaries.py:102`）直接 DENY。**INSERT 无 WHERE 也被拒**。
- `middleware/config.py:HITLConfig` 已把 `query_database` 列为需人工审核工具；`core/database/pool.py:db_pool.execute` 已存在写执行方法；`core/database/schema.py:schema_manager.clear_cache()` 已存在。

**目标**：同一 `query_database` 入口既能 SELECT 也能 INSERT/UPDATE/DELETE；边界靠既有管线（校验 + 三态 DENY + HITL）兜住，写后刷新 schema 缓存，返回受影响行数。

## 改动清单

- **修改**：`core/security/risk_assessor.py`
  - `_assess()` 无 WHERE 判定从「`is_write and 'WHERE' not in upper`」改为「(`dml`∈{UPDATE,DELETE}) 且无 WHERE」。INSERT 不再触发 `NO_WHERE_CLAUSE`。
  - 同步 `recommendations` 文案明确「UPDATE/DELETE 必须带 WHERE；INSERT 除外」。
  - 效果矩阵：`DELETE FROM sales`（无 WHERE）→ 仍 CRITICAL→DENY；`DELETE FROM sales WHERE id=3` → HIGH→CONFIRM→HITL；`INSERT INTO sales(...) VALUES(...)` → HIGH→CONFIRM→HITL（不再 DENY）。

- **修改**：`tools/sql_tools.py:query_database`
  - 新增 `_is_write_dml(sql)`：`sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE'))`。
  - `guard_query_sql` 通过后分派：
    - 写：`tag = await db_pool.execute(sql, timeout=timeout)` → 解析 tag 尾部整数得 `affected` → `await schema_manager.clear_cache()` → 返回 `QueryResult(success=True, row_count=affected, data=[{“操作”:dml, “受影响行数”:affected}], execution_time=...)`；**不入 result_store**。
    - SELECT：沿用 `db_pool.fetch` + `set_result`。
  - 更新 docstring 写操作语义；`except` 分支不变（瞬时 `raise` / 逻辑错误转自纠，对写同样适用）。

- **修改**：`agent/prompts.py`
  - 新增写操作边界小节：INSERT 用显式列名 `INSERT INTO ... (cols) VALUES (...)`；DELETE 必须 `WHERE` 限定范围；UPDATE 必须 `WHERE`；写操作会触发人工审核；完成后回述受影响行数。不硬编码示例表名。

- **修改**：`README.md` / `CHANGELOG.md`（用户可见变更 / 记录性变更）。

- **新增**：
  - `tests/test_risk_assessor.py`：INSERT 无 WHERE 不 DENY；DELETE/UPDATE 无 WHERE 仍 DENY；带 WHERE DELETE → CONFIRM。
  - `tests/test_sql_tools_write.py`：写路径返回受影响行数、清除 schema 缓存、写结果不入 result_store；SELECT 路径不受影响。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 写入口 | 复用 query_database | HITL 门禁已挂其上；改动最小；避免重复实现(Avoid#4) | tool 语义从「查询」扩展到「读写」，docstring/提示词需说清 |
| 写后返回 | 受影响行数 | 简洁；写结果本不适合作图表缓存 | 无法让用户直接看到新行（需二次 SELECT 查看） |
| 写后缓存 | 清 schema 缓存 | 避免 row_count/sample_data 长期 stale | 多 worker 下仅清当前 worker 内存缓存（默认单 worker，可接受） |
| INSERT 边界 | 无 WHERE 不判危险 | INSERT 语义上本无 WHERE；否则「加数据」被误杀 | 需在测试中锁死「INSERT 不 DENY、DELETE/UPDATE 仍 DENY」对照 |
| 结果展示 | data=[{操作,受影响行数}] | 复用既有表格渲染，零路由改动 | 表格只有一行汇总，不展示写入内容 |

## 兼容性

- 不破坏现有 API 响应/前端字段：写操作复用 `QueryResult`（沿用 `success/row_count/data`）。SELECT 路径完全不变。
- 配置默认值向后兼容：不新增配置，复用 `enable_sql_write`（默认 False；须显式开启才放行写操作）。
- 既有 `tests/test_security.py:120 test_write_without_where_is_critical` 用 DELETE，放宽仅影响 INSERT，该用例不受影响（已核对）。

## 测试计划

- `tests/test_risk_assessor.py`：INSERT / UPDATE / DELETE、带无带 WHERE 的对照断言。
- `tests/test_sql_tools_write.py`：mock `db_pool.execute`/`schema_manager.clear_cache`/`set_result`，断言写分派、行数返回、缓存清空、不入 result_store；SELECT 不受影响。
- `py -m pytest tests/ -q` 全绿。