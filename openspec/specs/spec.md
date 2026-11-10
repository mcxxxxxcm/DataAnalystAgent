# Text2SQL 分析 Agent 能力规格（汇总）

> 单文件汇总全系统当前已落地能力，作为后续改动的基线。中文说明，英文保留结构性关键词。
> 每个需求以 `CAP-xxx` 标识。Status 维护在文末「Specs 状态表」。
> 未实装的候选能力记录在 Specs 状态表备注列，不占正式需求，避免过度承诺。

---

## 1. Configuration（config/）

### 需求
| ID | 需求 | 现状 |
|----|------|------|
| CAP-CONF-001 | 集中配置：pydantic-settings 单例，`get_settings()` 经 `lru_cache` 全局唯一 | ✅ `config/settings.py` |
| CAP-CONF-002 | 分组配置项齐全且全部带默认值：LLM / DB / 安全 / 工具 / SchemaLinking / HITL审计 / 记忆 / 载荷裁剪 / 导出 / Agent / API | ✅ |
| CAP-CONF-003 | 敏感值从 `.env` 加载，不硬编码进代码（`extra="ignore"`、`case_sensitive=False`） | ✅ |
| CAP-CONF-004 | 由模型名推断上下文窗口，供摘要预算用（`context_budget = window × 0.8`） | ✅ |
| CAP-CONF-005 | 用户同义词映射可配置（`schema_synonyms`），供 schema linking 回退 | ✅ |

## 2. Core：database（core/database/）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-DB-001 | 异步连接池（asyncpg），`fetch(sql, timeout)` 严格执行超时 | ✅ `pool.py` |
| CAP-DB-002 | Schema 管理：list_tables / get_table_schema / get_sample_data | ✅ `schema.py` |
| CAP-DB-003 | 相关表召回（schema linking）：按相关性评分排序、上限 `schema_max_relevant_tables`、命中理由；可选语义重排 `rerank_with_embeddings`（关键词分 + embed 相似度加权，`schema_embed_enabled` 默认关零变化、失败静默回退关键词） | ✅ `schema_linking.py` |
| CAP-DB-004 | 低基数列样例值抓取开关（`schema_value_profiling`） | ✅ |
| CAP-DB-005 | 表/结构缓存有界（不无界增长） | ✅ |

## 3. Core：security（core/security/）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-SEC-001 | SQL 多层校验：AST 解析 / 关键字·危险函数黑名单 / 注入检测 / 多语句攻击检测 | ✅ `sql_validator.py` |
| CAP-SEC-002 | SQL 清理：规范化 + 危险注释移除 + 自动 LIMIT（钳制到 `sql_max_rows`） | ✅ `sql_sanitizer.py` |
| CAP-SEC-003 | 风险三态评估 ALLOW/CONFIRM/DENY：CRITICAL→DENY、HIGH/MEDIUM→CONFIRM、LOW/SAFE→ALLOW | ✅ `risk_assessor.py` |
| CAP-SEC-004 | 敏感表识别 + 自然语言回述（供 HITL 展示） | ✅ `risk_assessor.py` / `sql_to_natural_language.py` |
| CAP-SEC-005 | 结构化 SQL 错误自纠：13 类错误分类 + SQLSTATE + 修复建议，回喂 LLM 驱动重试 | ✅ `sql_error.py` |
| CAP-SEC-006 | 写操作默认不放行：`enable_sql_write` 为 False 时写 SQL 校验失败 | ✅ |
| CAP-SEC-007 | 任意代码执行默认关：`create_custom_chart` 仅显式 `enable_custom_chart=True` 才进工具集 | ✅ `tools/__init__.py` |
| CAP-SEC-008 | 写操作受边界保护：`query_database` 分派 INSERT/UPDATE/DELETE → 返回受影响行数、写后失效 schema 缓存、不入 result_store；`enable_sql_write` 默认关 + HITL 强制人审；DELETE/UPDATE 无 WHERE 仍 DENY。写语句带 `RETURNING` 时走 fetch 抓回写入行回显 data/columns（仍不入 store）；多行 `VALUES (...),(...)` 即单条批量插入 | ✅ `tools/sql_tools.py` |
| CAP-SEC-009 | 确定性意图路由器 `intent_guard`：NL 分类 query/chart/info/malicious/smalltalk/ambiguous/out_of_scope，带 deny/clarify 语义；`maybe_short_circuit` 已接线 `/query`（受 `ENABLE_INTENT_ROUTER` 门控，默认关、只短路 deny 不短路 clarify） | ✅ `core/security/intent_guard.py` / `api/routes.py` |
| CAP-SEC-010 | 确定性请求准入门 `admission_gate`：来源×意图合成准入判定（admit/deny/clarify/reply），迁移 dsh 的 Policy/gate/admission-table + 注意力经济；`maybe_gate` 接线 `/query`（`enable_admission_gate` 门控，默认关、只短路 deny/reply 不短路 clarify）；allowlist 模式校验 `X-Admission-Key`；寒暄/结构询问固定直答不烧 LLM | ✅ `core/security/admission.py` / `api/routes.py` / `config/settings.py` |
| CAP-SEC-011 | 注入检测加固：拦截「恒真/恒假布尔注入」——仅当比较符**两侧都是字面量**（`数字=数字`、`'串'='串'`）才拒绝；`列='值'`/`列>数字` 左是标识符不命中 → 不误杀；收掉恒真 `OR '1'='1'` 待办 | ✅ `core/security/sql_validator.py`（`TAUTOLOGY_PATTERNS`） |
| CAP-SEC-012 | 表/列级 RBAC 最小授权：按来源 key → 角色（`RolePolicy`/`Policy.from_json`），注入「系统表白名单 → 角色表/列白名单」additive 组合 checker；列越权拒绝、列提取失败 fail-closed；未匹配来源可回退 `default_role` 或拒绝 | ✅ `core/security/rbac.py` + `tools/boundaries.py` + `tools/sql_tools.py`（`enable_rbac` 默认关零变化） |
| CAP-SEC-013 | 滑动窗口限流/配额：per-key `deque[float]` 时间戳、key 上限防无界、惰性清过期；`parse_rate_limit` 解析 `"N/s|m|h|d"`；`RBAC_RATE_LIMIT` 配置、auth 后中间件 429 | ✅ `core/security/rate_limit.py` + `api/main.py`（`enable_rbac` + `rbac_rate_limit`，默认关 no-op） |

## 4. Tools（tools/）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-TOOL-001 | SQL 只读工具集：query_database / list_tables / get_table_schema / get_sample_data / get_relevant_schemas | ✅ `sql_tools.py` |
| CAP-TOOL-002 | `query_database` 执行前过统一守卫 `guard_query_sql`（校验 + 系统表拒绝 + 表白名单 + LIMIT + 三态门禁） | ✅ `boundaries.py` |
| CAP-TOOL-003 | 统一返回模型 + 序列化/反序列化：`QueryResult` 等 Pydantic 模型，`dump_result` / `parse_tool_result` | ✅ `result_schemas.py` |
| CAP-TOOL-004 | 声明式图表 `create_chart`：按 result_id 取数 → 服务端构建 ECharts option → 返回 option_id；字段缺失精确报错、图型自动推荐 | ✅ `chart_tools.py` + `utils/chart_spec.py` |
| CAP-TOOL-005 | 自定义绘图 `create_custom_chart`（matplotlib 任意代码）受能力门控，线程池 + 沙箱执行顺延兜住死循环 | ✅ 默认不暴露 |
| CAP-TOOL-006 | 分析工具：statistical_summary / data_profile / export_result（写本地文件需更高权限） | ✅ `analysis_tools.py` |
| CAP-TOOL-007 | 长期记忆工具 remember / recall（`enable_memory_tools` 控制） | ✅ `memory_tools.py` |
| CAP-TOOL-008 | 工具级权限子集 full / read_only / query_only，`get_enabled_tools(scope)` 选择；未知 scope 回退 full | ✅ `tools/__init__.py` |
| CAP-TOOL-009 | 系统表黑名单一致去重（`boundaries.SYSTEM_TABLES` 与 `schema.py` 同源），禁止查询 checkpoint/store 表 | ✅ |

## 5. Agent（agent/）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-AGENT-001 | 同步/异步两种 agent 构建，能力一致；异步用 AsyncPostgresSaver 持久化短期记忆 | ✅ `analyst_agent.py` |
| CAP-AGENT-002 | 系统提示词工作流：先 get_relevant_schemas 再执行、图表先查询取 result_id、不臆造表/列名、SQL 自纠规则 | ✅ `prompts.py` |
| CAP-AGENT-003 | 载荷裁剪中间件（跨轮压缩 ToolMessage，`condense_tool_results`） | ✅ |
| CAP-AGENT-004 | 长上下文自动摘要（官方 SummarizationMiddleware，token 预算触发） | ✅ |
| CAP-AGENT-005 | 瞬时/可恢复 SQL 错误自动重试（ToolRetryMiddleware，`sql_retry_on_transient`） | ✅ `middleware/config.py` |
| CAP-AGENT-006 | 错误格式化：工具异常统一封装为结构化 ToolError，避免裸 str(e) 回喂 | ✅ |
| CAP-AGENT-007 | 提示词缓存省计费：`prompt_cache_enabled=True` 时固定系统段尾插 marker、动态 `db_info`/`custom_instructions` 置尾（固定前置命中 provider 自动磁盘缓存）；`prompt_cache_header_json` 配置时经 `model_kwargs.extra_body` 注入显式 cache 头；off 时输出逐字节不变 | ✅ `agent/prompt_cache.py` + `agent/prompts.py` + `agent/analyst_agent.py` |

## 6. Middleware

| ID | 需求 | 现状 |
|----|------|------|
| CAP-MID-001 | 本地日志中间件（logging_middleware） | ✅ |
| CAP-MID-002 | HITL 中断配置：query_database 需审核，只读工具自动放行 | ✅ `middleware/config.py` |
| CAP-MID-003 | Checkpointer：优先 AsyncPostgresSaver，失败回退 InMemorySaver | ✅ |
| CAP-MID-004 | 长期记忆 Store：AsyncPostgresStore，初始化失败静默降级（记忆为加分项，非强依赖） | ✅ |

## 7. API + Frontend（api/ + static/）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-API-001 | 核心端点：`/api/query`（带 thread 记忆）、`/api/approve`（HITL）、`/api/state/{thread}`、`/api/export/{file}`、`/api/chart/option/{id}`、`/api/health`、`/api/logs`、`/api/stream/{thread}`、`/api/checkpoints/cleanup` | ✅ `routes.py` |
| CAP-API-002 | 可选 Bearer Token 鉴权：`API_AUTH_TOKEN` 非空时全部 `/api/**` 需 `Authorization: Bearer`；恒定时间比较 | ✅ `api/main.py` |
| CAP-API-003 | CORS 安全：`allow_origins` 从配置读取；`*` 时禁用 credentials，避免 `[*]+credentials` 组合 | ✅ |
| CAP-API-004 | 前端：查询交互 + 会话管理 + ECharts 矢量渲染 + HITL 批准/拒绝界面 | ✅ `static/index.html` |
| CAP-API-005 | `/api/query` 返回提取最后一个成功查询的结果（columns / data / markdown 表格） | ✅ |
| CAP-API-006 | 可观测只读端点 `GET /api/stats`：连接池（size/min/max/idle）、线程池配置、结果缓存条目数（供压测闭环调参） | ✅ `api/routes.py` |
| CAP-API-007 | checkpoint 维护端点：`/api/checkpoints/stats`、`/api/checkpoints/cleanup`（dry_run 默认开）、`/api/checkpoints/cleanup-orphaned` | ✅ `api/routes.py` |
| CAP-API-008 | 可观测 `/api/metrics`：`observability_enabled=True` 时暴露 Prometheus 文本（工具耗时/请求计数延迟/连接池+result_cache gauge），否则 404；请求计数/延迟中间件门控 | ✅ `api/routes.py` + `api/main.py` + `observability/` |

## 8. Utils

| ID | 需求 | 现状 |
|----|------|------|
| CAP-UTIL-001 | 查询结果引用缓存有界 TTL（上限 50 条 / 10 分钟过期） | ✅ `utils/result_store.py`（代理到 `BoundedTTLCache`） |
| CAP-UTIL-006 | 单一写者有界 TTL 缓存原语 `BoundedTTLCache`：写/淘汰集中于一个类，读（get/peek）非摧毁式、pop 显式一次性消费；状态所有权约定见 `docs/state-owners.md`；消除 result_store 与图表 spec 缓存的手写重复实现 | ✅ `utils/bounded_cache.py` |
| CAP-UTIL-007 | 持久化效果队列 `AsyncEffectQueue`：可重试副作用按 (kind,key) 幂等入队、指数退避重试、可选 JSONL 持久化、pending/settled/failed 健康计数；`run_sql_durable` 接通 SQL 瞬时错误退避层（`effect_queue_max_retries>0`，默认 2） | ✅ `utils/effect_queue.py` / `tools/sql_tools.py` |
| CAP-UTIL-002 | ECharts option 构建器 `build_echarts_option`（dataset + encode，字段缺失精确报错） | ✅ `utils/chart_spec.py` |
| CAP-UTIL-003 | 导出管理 export_manager（CSV/XLSX，`export_max_rows` 采样上限） | ✅ |
| CAP-UTIL-004 | 图表代码沙箱 `execute_chart_code`（安全 globals，非危险） + checkpoint 清理 | ✅ `chart_sandbox.py` / `checkpoint_cleanup.py` |
| CAP-UTIL-005 | 并发压测工具 `bench.loadtest`：health/ping/query 端点、thread-mode（unique/reuse/per-worker）、`--dry-run`、Bearer 鉴权 | ✅ `bench/loadtest.py` |
| CAP-UTIL-008 | 缓存后端抽象：`CacheBackend` Protocol（set/get/peek/pop/clear/size/keys，与 `BoundedTTLCache` 同构）、`MemoryCacheBackend`（内部持 `BoundedTTLCache`，单一写者）、`RedisCacheBackend`（`redis.asyncio` + 同步面 `run_coroutine_threadsafe` 桥、JSON 序列化 datetime/Decimal、ZSET 容量淘汰、key 命名空间）、`get_cache_backend`（redis 不可达回退 memory）；result_store（`rs:`）/ chart_tools（`chart:`）签名不变 | ✅ `utils/cache_backend.py` + `utils/result_store.py` + `tools/chart_tools.py` |

## 9. Eval & Tests

| ID | 需求 | 现状 |
|----|------|------|
| CAP-EVAL-001 | Text2SQL 回归评测：`eval/run_eval.py` 多场景聚合 harness，跑分类语料 | ✅ |
| CAP-EVAL-002 | 分类语料：`eval/cases/`（schema_linking / security_deny / routing_guard 三文件，41 例），另含 `mine_badcases.py` 扫日志 dump / 自动沉淀坏 case | ✅ `schema_linking.json`（11）/ `security_deny.json`（13）/ `routing_guard.json`（17） |
| CAP-EVAL-003 | 单元测试：安全校验 / 工具边界 / 载荷裁剪 / 返回结构 / SQL 错误 / 图表 spec / 写操作 / 意图路由器 / 评测回归 / 并发 / 模型视图重建 / 准入门 / 单一写者 / 效果队列 / 注入加固 / 写 RETURNING / 语义重排 / 坏case沉淀 | ✅ `tests/`（203 项通过，`py -m pytest tests/ -q`） |
| CAP-EVAL-004 | `pytest tests/ -q` 为改动硬门槛 | ✅ |
| CAP-EVAL-005 | 坏 case 自动沉淀：`mine_badcases --sink-security [--apply]` 把被安全/校验层拒绝的 `query_database` 失败调用按规范化 SQL 去重写进 `security_deny.json`（默认 dry-run、幂等） | ✅ `eval/mine_badcases.py` |

## 10. Core：recon（模型视图可重建不变量，M1）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-RECON-001 | 确定性重建：`reconstruct_model_messages(events)` 把会话事件编排成 LangChain 消息序列；`session_events_from_tool_records` 把工具日志转事件；纯函数、无 DB/LLM | ✅ `core/recon.py` |
| CAP-RECON-002 | 忠实捕获：工具日志记录真实 `thread_id`（来自 `request.runtime.config`，回退 `'current'`）+ `model_view`（与送入 LLM 同 condense 阈值）；`recon_model_view_enabled` 门控（默认开） | ✅ `middleware/logging_wrapper.py` / `config/settings.py` |

## 11. Observability（observability/）

| ID | 需求 | 现状 |
|----|------|------|
| CAP-OBS-001 | 纯 stdlib Prometheus 文本指标：`record_tool`/`record_request`/`refresh_pool` + `render_metrics`；`setup_observability`/`enabled` 读 `observability_enabled`，关时全 no-op | ✅ `observability/metrics.py` + `observability/__init__.py` + `middleware/logging_wrapper.py` |

---

## Specs 状态表

| 能力域 | 状态 | 备注（候选/风险） |
|--------|------|-------------------|
| Configuration | implemented | 少设置审计：删除 4 个无消费方配置（`db_max_overflow`/`cache_ttl`/`redis_url`/`agent_verbose`），运行时常量以模块常量为准 |
| core/database | implemented | schema linking 关键词打分打底，可选 Embedding 语义重排已落地（CAP-DB-003，`schema_embed_enabled` 默认关 + 失败回退关键词） |
| core/security | implemented | 写操作已落地（CAP-SEC-008 + RETURNING 回看）；意图路由器已接线（CAP-SEC-009）；请求准入门 `admission_gate` 已落地（CAP-SEC-010）；注入检测加固恒真假字符文本拦（CAP-SEC-011）；表/列 RBAC + 滑动窗口限流已落地（CAP-SEC-012/013，默认关零变化） |
| Tools | implemented | `create_custom_chart` 默认禁用（安全设计）；写操作由 `query_database` 分派（CAP-SEC-008）；缓存后端可切 Redis（CAP-UTIL-008） |
| Agent | implemented | 同步/异步两版能力对齐：载荷裁剪（condense_tool_results）+ 长上下文摘要 + 瞬时重试均具备；提示词缓存省计费（CAP-AGENT-007，默认关） |
| Middleware | implemented | — |
| API + Frontend | implemented | 新增 `/api/stats`（CAP-API-006）、checkpoint 维护端点（CAP-API-007）、`/api/metrics`（CAP-API-008，`observability_enabled` 默认关，`observability/` 纯 stdlib 采集 CAP-OBS-001） |
| Utils | implemented | 新增 `bench.loadtest`（CAP-UTIL-005）；单一写者缓存原语 `BoundedTTLCache`（CAP-UTIL-006）；持久化效果队列（CAP-UTIL-007，SQL 瞬时后退避层）；缓存后端抽象 memory/Redis（CAP-UTIL-008） |
| Eval & Tests | implemented | 语料扩集 41 例（schema_linking 11 / security_deny 13 / routing_guard 17）；含写操作/意图路由/并发/注入加固/语义重排/坏case沉淀/提示词缓存/缓存后端/可观测/RBAC/限流回归测试；`mine_badcases --sink-security` 自动沉淀坏 case |
| recon（可观测） | implemented | 模型视图可重建不变量（CAP-RECON-001/002，change：recon-model-view-invariant） |