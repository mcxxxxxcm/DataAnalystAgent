# Change Proposal：4 项 backlog 一次补齐（B005/B006/B007/B010）

设计文档，给 review。四段独立能力，各自带测试与配置；**全部默认关，additive 注入，不破坏现状**。

---

## 段 1 —— B005 LLM 提示词缓存省计费（P0）

### 现状 → 目标
- 现状：`agent/prompts.py` 的 `SYSTEM_PROMPT`（固定段）+ `build_system_prompt()` 把动态 `db_info`/`custom_instructions` 直接拼到固定段后面（`agent/analyst_agent.py` 建 `ChatOpenAI`，`base_url` 兼容 DeepSeek OAI 协议）。同一提示词每轮全量计费，无缓存优化。
- 目标：让固定提示词前缀**稳定置顶、动态段置尾**，命中支持自动磁盘缓存的 provider（省重复计费 token）；可选显式 cache 头注入。

### 改动清单
- 新建 `agent/prompt_cache.py`：
  - `_MARKER = "\n\n## 以下为本轮动态部分(随会话变化,不参与稳定缓存)\n"`
  - `split_cached_prompt(prompt) -> tuple[固定段, 动态段] | None`（按 marker 切；无 marker 返回 None）。
  - `build_cache_kwargs(prompt, header_json: str) -> dict | None`（解析 header_json 为注入的 extra_body；空/非法返回 None）。
- 修改 `agent/prompts.py`：`build_system_prompt()` 增加参数（内部读 `settings.prompt_cache_enabled`）——开启时在固定段尾插 marker 再拼动态段；**关闭时字节级保持现输出不变**。
- 修改 `agent/analyst_agent.py`（同步 ~75-80 / 异步 ~164-169）：`prompt_cache_enabled` 时经 `model_kwargs={"extra_body": build_cache_kwargs(...)}` 注入显式头（仅当 header_json 配置）。
- 配置 `config/settings.py`：新组「提示词缓存」：
  - `prompt_cache_enabled: bool = False`
  - `prompt_cache_header_json: str = ""`（显式 cache 头 JSON 字面量，空=不注入）

### 取舍 / 风险
| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 缓存策略 | 固定前置+动态置尾（自动磁盘缓存友好）| provider 是 base_url 兼容的 OAI 协议，无标准 cache_control | 需 provider 支持自动缓存才生效，属「尽力」 |
| 显式头 | 默认关 | 不同 provider 头格式不一，注入可能报错 | 收益被门控，需按 provider 自行配 |

### 测试计划
`tests/test_prompt_cache.py`：off 时 `build_system_prompt` 输出逐字节同现状；on 时固定段稳定/动态段置尾；`split_cached_prompt` 切分正确；LLM 构造开/关 header 正确。

---

## 段 2 —— B006 多 worker + Redis 共享缓存（P2）

### 现状 → 目标
- 现状：`utils/result_store.py` 持单例 `_BoundedTTLCache`（50/600 内置默认）；`tools/chart_tools.py` 持 `_spec_cache`；均为每进程内存，扩 worker 后 result_id / option_id 跨 worker 404。
- 目标：抽出「缓存后端抽象」，memory 用现有 `BoundedTTLCache`，redis 用 `redis.asyncio`；保持 `docs/state-owners.md` 不变量（单一写者 / TTL·容量有界 / 非破坏读）。

### 改动清单
- 新建 `utils/cache_backend.py`：
  - `CacheBackend`（Protocol：`set/get/peek/pop/clear/size/keys`，与 `BoundedTTLCache` 同构）。
  - `MemoryCacheBackend`：内部持一个 `BoundedTTLCache`（单一写者不变）。
  - `RedisCacheBackend`：内部 `redis.asyncio.Redis`；同步面经 `run_coroutine_threadsafe` 桥到独立后台 event loop；value 走 JSON（自定义 `default=` 处理 datetime/Decimal）→ `SETEX key json ex=ttl`；容量有界用 ZSET 记写入时间戳、超 `max_entries` 淘汰最旧；key 加命名空间前缀（防跨 owner 串写）。
  - `get_cache_backend()`：按 `settings.cache_backend` 选；redis import 失败 / 连不上 → `logging.warning` 后回退 `MemoryCacheBackend`（对齐 checkpointer/长期记忆的降级）。
- 修改 `utils/result_store.py`：`_cache = get_cache_backend()`（命名空间 `rs:`）；函数签名不变。
- 修改 `tools/chart_tools.py`：`_spec_cache = get_cache_backend()`（命名空间 `chart:`）；函数签名不变。
- 配置 `config/settings.py`：新组「缓存后端」：
  - `cache_backend: str = "memory"`（`memory` / `redis`）
  - `redis_url: str = ""`（**重新引入**——few-settings 审计曾删此项；理由：B006 明确需要一个可选共享缓存落点，且默认空=memory 不改变「少设置」原则）

### 取舍 / 风险
| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 后端抽象 | 与 BoundedTTLCache 同构 Protocol | 接口稳定，result_store/chart 改一行即切 | 抽象层需保不变量 |
| 同步/异步桥 | run_coroutine_threadsafe 后台 loop | 现有调用面是同步，不必动调用方 | 后台 loop 生命周期要管理好 |
| 容量边界 | 应用层 ZSET | 不依赖 Redis maxmemory，行为同 memory | 略增命令数 |
| Redis 依赖 | 可选 | 未装/连不上回退 memory | 需在需求文件标注 optional |

### 测试计划
`tests/test_cache_backend.py`：双后端七方法同构；TTL 过期 get=None 且淘汰；超容量淘汰最旧；datetime 序列化往返；redis 不可达回退 memory；存量 `test_single_writer.py` / `test_sql_tools.py` 仍绿。

---

## 段 3 —— B007 可观测 `/metrics`（P1）

### 现状 → 目标
- 现状：`GET /api/stats`（`api/routes.py`）返回 db_pool/thread_pool/result_cache 快照；`middleware/logging_wrapper.py` 已记录工具耗时/状态。
- 目标：新增 Prometheus 文本 `GET /metrics`（工具耗时、请求计数/延迟、连接池状态），复用现有埋点与 stats 数据。

### 改动清单
- 新建 `observability/`：
  - `observability/metrics.py`：`record_tool(name, ms, success)`、`record_request(method, path, status, ms)`、`refresh_pool(...)` + `render_metrics() -> str`（Prometheus 文本格式）。
  - `observability/__init__.py`：`setup_observability()` / `enabled()`（读 `settings.observability_enabled`，关时 no-op）。
- 修改 `middleware/logging_wrapper.py`：success/failure 分支调用 `record_tool`（门控）。
- 修改 `api/routes.py`：加 `GET /metrics`（`enabled` 才暴露，否则 404）；`/stats` 处理里刷新 pool/result_cache gauge。
- 修改 `api/main.py`：请求计数/延迟中间件（门控）。
- 配置：`observability_enabled: bool = False`。
- 依赖：`prometheus-client`（轻量纯 py）加入 `requirements.txt`。

### 取舍 / 风险
| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 实现路径 | prometheus-client 文本格式 | `/metrics` 是标准消费格式，且 OTel Prometheus 导出器同格式；不引完整 OTel SDK（重） | 非 OTel API，追踪留接口待后续 |

### 测试计划
`tests/test_observability.py`：`record_tool` 后文本含计数/耗时 histogram；`render_metrics` 输出合法；`enabled` 关时 `record_tool` 为 no-op。

---

## 段 4 —— B010 表/列级 RBAC + 速率限制/配额（P2）

### 现状 → 目标
- 现状：`api/main.py` 单 `API_AUTH_TOKEN` 鉴权 + `TOOL_SETS` scope；`tools/boundaries.py` 有 `SYSTEM_TABLES` + `is_allowed_table` + `guard_query_sql`（可选 `table_checker`）；无用户/角色与限流。
- 目标：多角色最小授权（表/列白名单 + 工具 scope）+ 每来源/每 token 滑动窗口限流；默认关不覆盖现有守卫。

### 改动清单
- 新建 `core/security/rbac.py`：
  - `RolePolicy` dataclass：`role: str`、`tables: set[str] | None`（None=沿用现白名单）、`columns: dict[str, set[str]]`、`tools_scope: str`。
  - `PolicyLoader.from_json(text: str)`（解析 `rbac_policy_json` 字面量或 `@path`）。
  - `resolve_role(source_key: str | None, policy) -> str | None`（来源 key → 角色；未配置回退默认）。
- 新建 `core/security/rate_limit.py`：
  - `SlidingWindowLimiter`: `__init__(limit: int, window_seconds: float, max_keys: int)`，`allow(key) -> bool`（每个 key 一个 `deque[float]` 时间戳，惰性清过期；key 上限防无界）。
  - `parse_rate_limit(spec: str) -> SlidingWindowLimiter | None`（如 `"10/min"`，空/非法返回 None）。
- 修改 `tools/boundaries.py`：`guard_query_sql` 加可选 `column_checker=None`（与 `table_checker` 并列）；缺省 None 时路径与现状完全一致。
- 修改 `tools/sql_tools.py` `query_database`：RBAC 开启时注入「现 `is_allowed_table` → 角色表/列白名单」的**组合 checker**（additive，非覆盖）；列提取失败 fail-closed 拒绝。
- 修改 `api/main.py`：auth 后加限流中间件（`enable_rbac` + `rbac_rate_limit` 时）；`api/routes.py` `/query` 解析 role 注入工具 scope。
- 配置「RBAC」组：
  - `enable_rbac: bool = False`
  - `rbac_policy_json: str = ""`
  - `rbac_rate_limit: str = ""`（如 `"10/min"`）

### 取舍 / 风险
| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 列级提取 | sqlparse 解析 + fail-closed | 复杂查询解析失败宁可拒 | 误伤复杂查询，需策略谨慎 |
| 守卫扩展 | additive 组合 checker | RBAC off 时守卫逐字节不变 | 两层 checker 都要测 |

### 测试计划
`tests/test_rbac.py` + `tests/test_rate_limit.py`：角色解析；越权表/列拒绝、系统表仍拒；RBAC off 时守卫行为逐例一致（跑现有 `test_tool_boundaries`）；限下放行/超限拒绝/窗口滑动/per-key 隔离/off no-op。

---

## 兼容性
- 四段新配置默认 `False` / `"memory"` / `""`，不影响现有行为与 API 响应字段。
- `guard_query_sql` 新增参数带默认，向后兼容；`result_store`/`chart_tools` 对外函数签名不变。
- `redis_url` 重新引入但默认空、未用 Redis 时行为同 memory。
- 新增 `prometheus-client` 依赖（轻量）。

## Global 依赖 / 风险
- 仅新增 `prometheus-client`（轻量纯 py）进 requirements；`redis[asyncio]` 作**可选**（未装回退 memory）。
- 边界：不引入完整 OTel SDK；不做多用户登录系统（角色由来源/token 映射，非认证）。