# Change Recipe：4 项 backlog 一次补齐（执行剧本）

> 给 LLM 的逐步执行清单。执行后对着每步 Validation 打 `[x]`。执行顺序：段2 → 段3 → 段4 → 段1（段2 的接口是其它段的底座）。

## Step 1 —— 读约定与验证基线
- **Context**: 对齐项目宪法，且先确认改动前测试基线是绿的，避免把非本 change 的失败算进来。
- **Action**: 读 `openspec/agreement.md`；跑一次 `pytest tests/ -q` 记下行数作为基线。
- **Validation**: 确认四个新包/文件落在正确分层（utils/core/config/agent/middleware/api/observability）；基线全绿。 `[x]`

---

## 段 2 —— B006 缓存后端抽象

## Step 2 —— 新建 `utils/cache_backend.py`
- **Context**: 缓存后端可切换、且接口与现有 `BoundedTTLCache` 同构，是 result_store/chart 最小改动的地基。
- **Action**: 读 `utils/bounded_cache.py` 取其接口。新建 `CacheBackend` Protocol、`MemoryCacheBackend`、`RedisCacheBackend`、`get_cache_backend()`。Redis 后端：同步面桥 `run_coroutine_threadsafe` 到模块级后台 loop；value JSON 序列化（datetime/Decimal）→ `SETEX ... ex=ttl`；ZSET 记写入时间戳做容量淘汰；key 命名空间前缀参数。`get_cache_backend` 读 `settings.cache_backend`/`settings.redis_url`，redis 失败 `logging.warning` 回退 memory。
- **Validation**: `python -c "from utils.cache_backend import get_cache_backend; b=get_cache_backend(); b.set('k',{'n':1}); assert b.get('k')=={'n':1}"`（默认 memory 路径通）。 `[x]`

## Step 3 —— 接入 result_store / chart_tools
- **Context**: 让结果缓存与图表 spec 缓存底层可切换，保持单一写者不变量。
- **Action**: 读 `utils/result_store.py` 与 `tools/chart_tools.py`，将内部缓存改为 `get_cache_backend()`（分别传命名空间 `rs:` / `chart:`），**保持对外函数签名不变**。
- **Validation**: `pytest tests/test_single_writer.py tests/test_sql_tools.py -q` 全绿（无 redis 时走 memory）。 `[x]`

## Step 4 —— 缓存后端配置 + 测试
- **Context**: 配置默认 memory，满足少设置原则；用测试锁定不变量。
- **Action**: `config/settings.py` 加 `cache_backend="memory"`、`redis_url=""`。新建 `tests/test_cache_backend.py`：双后端（redis 用 fakeredis 或跳过）七方法同构、TTL 过期淘汰、超容量淘汰最旧、datetime 往返、redis 不可达回退 memory。
- **Validation**: `pytest tests/test_cache_backend.py -q` 绿。 `[x]`

---

## 段 3 —— B007 可观测 /metrics

## Step 5 —— 新建 `observability/` 包
- **Context**: 统一指标采集，Prometheus 文本格式，门控 no-op。
- **Action**: 新建 `observability/metrics.py`（`record_tool`/`record_request`/`refresh_pool`/`render_metrics`）+ `observability/__init__.py`（`enabled()`/`setup_observability()`，读 `observability_enabled`）。
- **Validation**: `python -c "from observability import enabled; assert enabled() is False"`（默认关 no-op）。 `[x]`

## Step 6 —— 埋点接线
- **Context**: 复用现有日志埋点点位，最小侵入。
- **Action**: `middleware/logging_wrapper.py` success/failure 分支加 `record_tool`（门控）；`api/main.py` 加请求计数/延迟中间件（门控）；`api/routes.py` 加 `GET /metrics`（enabled 才暴露）+ `/stats` 刷新 gauge。
- **Validation**: `pytest tests/test_observability.py -q`（record 后文本含计数/耗时；enabled 关 no-op）；`/metrics` 开 200 / 关 404 由路由测试覆盖。 `[x]`

## Step 7 —— 依赖
- **Context**: 轻量纯 py，满足 /metrics 标准格式。
- **Action**: 【偏离】实际实现为**零新依赖**：`observability/metrics.py` 用纯标准库拼 Prometheus exposition 文本（`requirements.txt` 无新增），对齐「少设置/零依赖」偏好，功能与 prometheus-client 等价。
- **Validation**: `python -c "from observability.metrics import render_metrics; assert isinstance(render_metrics(), str)"`（纯 stdlib，无外部依赖）。 `[x]`

---

## 段 4 —— B010 RBAC + 限流

## Step 8 —— 新建 `core/security/rbac.py`
- **Context**: 角色策略最小授权，additive 不覆盖现有守卫。
- **Action**: 读 `tools/boundaries.py` 的 `guard_query_sql`/`is_allowed_table`/SYSTEM_TABLES。新建 `RolePolicy`、`PolicyLoader.from_json`、`resolve_role`；实现表/列白名单组合 checker（列提取失败 fail-closed）。
- **Validation**: 单测 `tests/test_rbac.py` 前若干用例（角色解析、越权表拒绝、系统表仍拒、列越权拒绝）。 `[x]`

## Step 9 —— `guard_query_sql` 加可选 column_checker + 接线
- **Context**: 列级白名单是 RBAC 的最小授权核心；缺省 None 时与现状完全一致。
- **Action**: `tools/boundaries.py` `guard_query_sql` 加 `column_checker=None`（与 `table_checker` 并列，逻辑同为非法即拒）；`tools/sql_tools.py` `query_database` RBAC 开启时注入组合 checker。
- **Validation**: `pytest tests/test_tool_boundaries.py -q` 全绿（证明 RBAC off 时守卫行为不变）；+ RBAC on 新增用例。 `[x]`

## Step 10 —— 限流 + API 接线 + 配置
- **Context**: 防滥用，默认关。
- **Action**: 新建 `core/security/rate_limit.py`（`SlidingWindowLimiter` + `parse_rate_limit`）；`api/main.py` auth 后加限流中间件；`api/routes.py` `/query` 解析 role 注入工具 scope；配置 `enable_rbac=False`、`rbac_policy_json=""`、`rbac_rate_limit=""`。
- **Validation**: `tests/test_rate_limit.py`（限下放行/超限拒绝/窗口滑动/per-key 隔离/off no-op）+ `tests/test_rbac.py` 全绿。 `[x]`

---

## 段 1 —— B005 提示词缓存

## Step 11 —— 新建 `agent/prompt_cache.py` + 改 `prompts.py`
- **Context**: 固定前缀置顶命中缓存；off 时字节级不变。
- **Action**: 读 `agent/prompts.py`。新建 `prompt_cache.py`（`_MARKER`/`split_cached_prompt`/`build_cache_kwargs`）；`build_system_prompt()` 读 `prompt_cache_enabled`，on 时插 marker 再拼动态段、off 时原样输出。
- **Validation**: `pytest tests/test_prompt_cache.py` 中 off 逐字节一致 / on 动态段置尾 / split 正确。 `[x]`

## Step 12 —— LLM 构造注入 + 配置 + 测试
- **Context**: 可选显式 cache 头，默认关。
- **Action**: `agent/analyst_agent.py` 同步/异步两处 `ChatOpenAI(...)` 在启用时 `model_kwargs={"extra_body": build_cache_kwargs(...)}`；配置 `prompt_cache_enabled=False`、`prompt_cache_header_json=""`；补 `tests/test_prompt_cache.py` LLM 构造用例。
- **Validation**: `pytest tests/test_prompt_cache.py -q` 全绿；`pytest tests/ -q` 全绿。 `[x]`

---

## Final —— 收尾自检
- 对照 `overview.md` 的 How 承诺逐条核对是否兑现。
- 更新 `README.md`（用户可见：4 项能力说明）+ 追加 `CHANGELOG.md`。
- 回填 `specs/spec.md` 对应 CAP、`tasks.md` 关掉 B005/B006/B007/B010 四个 `[todo]`、`docs/state-owners.md` 登记新外部状态 owner、`terminology.md` 视需补术语。
- change 目录移出 `changes/` → `archived/` 归档。
- `pytest tests/ -q` 全绿确认；提交信息中文一句主题 + `Co-Authored-By`。 `[x]`