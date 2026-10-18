# Change Overview：修复瞬时错误重试链路 + schema 缓存 TTL

## Why（为什么做）

三个缺陷叠加，导致「瞬时错误自动重试」与「schema 缓存失效」都形同虚设：`ToolErrorMiddleware()` 无参构造即崩（`create_agent` 因此失败）；`query_database` 用 `except Exception` 吞掉瞬时错误、使之永不进入 `ToolRetryMiddleware`；`get_table_schema` 用 `timedelta.seconds` 判断缓存、超一天后回绕为「永远新鲜」。

## What（做什么 / 不动什么）

- 修改：`middleware/config.py` —— 移除坏的 `ToolErrorMiddleware()`（与重试/自纠职责重叠）。
- 修改：`tools/sql_tools.py` —— `query_database` 对瞬时错误 `raise`，仅逻辑错误转 `success=false`。
- 修改：`core/database/schema.py` —— 缓存 TTL 判断 `.seconds` → `.total_seconds()`。
- 新增测试：`tests/test_sql_tools.py`、`tests/test_schema_cache.py`；`tests/test_tool_boundaries.py` 追加中间件构建用例。
- **不做**：不把缓存 TTL/Redis 落地进 `settings.py`（属 P1「配置空壳」，本期不做）；不动 HITL、不动其他工具、不改导出与图表。

- 影响层：middleware（构建链）、tools（错误分流）、core（缓存时效）。

## How（怎么落地，一句概览）

三处离散修复：移除坏中间件让中间件链可构建；`query_database` 用 `is_transient_error` 分流「瞬时错误 raise / 逻辑错误结构化失败」；schema 缓存用 `total_seconds()` 正确判过期。细节见 `recipe.md`。

---

- 关联 issue / 关联模块：`middleware/config.py` 的 get_middleware_list；`tools/sql_tools.py` 的 query_database；`core/database/schema.py` 的 get_table_schema
- 涉及测试：`tests/test_sql_tools.py`（新增）、`tests/test_schema_cache.py`（新增）、`tests/test_tool_boundaries.py`（追加）