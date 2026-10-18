# Change Proposal：修复瞬时错误重试链路 + schema 缓存 TTL

## 方案

### 现状 → 目标

**现状**

- `middleware/config.py:67` 写 `middlewares.append(ToolErrorMiddleware())`（无参），但当前版本 `ToolErrorMiddleware.__init__` 要求必须传 `on_error`/`aon_error`，否则抛 `ValueError`。实测 `get_middleware_list()` 直接崩，`create_agent()` 因此失败——重试中间件根本没被构建。
- `tools/sql_tools.py:53-57` `query_database` 用 `except Exception` 把**所有**异常（含瞬时连接中断/死锁/超时）吞掉转成 `success=false`，于是 `ToolRetryMiddleware.retry_on=is_transient_error` 永远等不到一个抛上来的瞬时异常，自动重试形同虚设。
- `core/database/schema.py:114` 用 `(datetime.now() - cache_time).seconds < self._cache_ttl`。`timedelta.seconds` 是 `[0, 86400)` 的模，跨过整数天后秒数回绕到接近 0，缓存对象会「永远新鲜」，表结构变更后不再刷新。

**目标**

- 让 `get_middleware_list()` 可正常构建，`ToolRetryMiddleware` 真正链入。
- 让瞬时 SQL 错误被 `ToolRetryMiddleware` 原样重试；逻辑错误仍走结构化 `success=false` 回喂 LLM 自纠。
- 让 schema 缓存在超过 TTL 后正确失效、重新拉取。

### 改动清单

- 修改 `middleware/config.py` —— 删除 `middlewares.append(ToolErrorMiddleware())` 一行，并摘除顶部 `ToolErrorMiddleware` 的 import（`ToolRetryMiddleware` 保留）。理由见取舍表。
- 修改 `tools/sql_tools.py` ——
  - import 行程 `from core.security.sql_error import is_transient_error, build_self_correction_message`。
  - `query_database` 的 `except Exception` 块，先 `if is_transient_error(e): raise`，否则维持现有结构化失败返回。
- 修改 `core/database/schema.py` —— 缓存判断改 `(datetime.now() - cache_time).total_seconds() < self._cache_ttl`。
- 新增测试：见「测试计划」。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| `ToolErrorMiddleware` 处置 | 移除 | 无参即崩从未生效；其「封装工具异常为结构化反馈」与 `ToolRetryMiddleware(on_failure="continue")` + `query_database` 自纠重叠，符合 agreement Avoid#4 不造重复实现 | 非 SQL 工具抛异常回退到 langgraph 默认的 error ToolMessage（含 `str(exc)`），不再有显式结构化封装 |
| 瞬时错误分流判定 | `is_transient_error(e)` | 复用现有单点判定（SQLSTATE + 关键字），与 `ToolRetryMiddleware.retry_on` 同源，口径一致 | 依赖 `is_transient_error` 覆盖面；漏判的瞬时错误仍走 success=false（可后续扩 marker） |
| TTL 判定 API | `total_seconds()` | 修正 `timedelta.seconds` 的模回绕 | 无行为代价，纯修复 |

## 兼容性

- `get_middleware_list()` 从此不再抛异常，返回中间件列表少一个 `ToolErrorMiddleware`——对外签名不变，仅越掉一个从未成功构造的项。
- `query_database` 对外契约不变：成功仍返回 `QueryResult` JSON；逻辑错误仍 `success=false` + 修复建议。唯一变化是瞬时错误由「返回 success=false」变为「抛异常给中间件重试」——这正是本次修复目标。
- 配置项无新增/变更，无默认值兼容问题。
- 不触及 API 响应字段、前端字段、导出/图表行为。

## 测试计划

- 新增 `tests/test_sql_tools.py`（沿用无 DB 的 monkeypatch 模式）：
  1. 瞬时错误（`sqlstate="08006"`、`str` 含 `connection`）→ `query_database.ainvoke` 抛出原异常（未被吞成 success=false）。
  2. 逻辑错误（`str` 含 `does not exist`）→ 返回 `success=false` 且 `error` 含「修复建议」/错误码。
- 新增 `tests/test_schema_cache.py`：
  3. 注入「1 天 + 10 秒」前的 `_cache_time`，`get_table_schema` 应重新查库（`db_pool.fetch` 被调用），验证 `total_seconds()` 修复；对照「10 秒前」的缓存应命中、不查库。
- `tests/test_tool_boundaries.py` 追加：
  4. `get_middleware_list()` 可构建、且列表含 `ToolRetryMiddleware`、不含 `ToolErrorMiddleware`。