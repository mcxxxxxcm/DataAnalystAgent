# 任务分解（Tasks）

> 项目级任务清单，给**执行 / 验收**用，回答「要拆成哪些可验收的任务、谁负责、怎么验收」。
> 编号规则：`TASK-xxx`。状态：`[done]` 已实现 / `[todo]` 候选未做（对齐 `specs/spec.md` 状态表与 `agreement.md` 候选，不虚构）。
> 每个任务映射到 `specs/spec.md` 的 CAP-xxx 能力号与 `design.md` 模块。验收以有权重方式列出可测项。
>
> **当前快照**：全系统大部分能力已落地（`spec.md` 状态表 implementation），故绝大多数 TASK 标 `[done]`；
> 未实现项集中在文末「候选 / backlog」(`[todo]`)。新改动按 `agreement.md` §2 走 change 流程，在对应 TASK 下挂后续。

---

## 1. 配置层（TASK-CONF-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-CONF-001 | [done] | 集中配置单例 + pydantic-settings | CAP-CONF-001 `config/settings.py` | `get_settings()` 全局唯一（lru_cache）；`SettingsConfigDict` 从 `.env` 加载、`extra=ignore`、`case_sensitive=False` |
| TASK-CONF-002 | [done] | 全量配置项分组、默认值完备 | CAP-CONF-002 `config/settings.py` | LLM/DB/安全/工具/SchemaLinking/HITL/记忆/裁剪/导出/Agent/API 各组不缺失；全部有默认值 |
| TASK-CONF-003 | [done] | 敏感值环境化、不硬编码 | CAP-CONF-003 | `api_key`/`db_password` 等经 `.env`；代码内无明文密钥 |
| TASK-CONF-004 | [done] | 上下文窗口推断 + 预算 | CAP-CONF-004 `context_budget` | `window×0.8`；`_infer_context_window` 按模型名回落 128k |
| TASK-CONF-005 | [done] | 用户同义词映射 | CAP-CONF-005 `user_synonym_map` | `schema_synonyms` 解析为 `{词:[表]}`，容错段格式 |

## 2. 数据库 / schema / schema linking（TASK-DB-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-DB-001 | [done] | 异步连接池与超时执行 | CAP-DB-001 `core/database/pool.py` | `fetch(sql, timeout)` 严格执行超时；连接池大小可配 |
| TASK-DB-002 | [done] | Schema 管理三件套 | CAP-DB-002 `core/database/schema.py` | list_tables / get_table_schema / get_sample_data 可用 |
| TASK-DB-003 | [done] | 相关表召回（schema linking） | CAP-DB-003 `schema_linking.py` | 相关性评分排序、上限 `schema_max_relevant_tables`、命中理由 |
| TASK-DB-004 | [done] | 低基数列样例抓取开关 | CAP-DB-004 | `schema_value_profiling` 开关生效 |
| TASK-DB-005 | [done] | 表/结构缓存有界 | CAP-DB-005 | 缓存带容量/TTL，不无界增长 |
| TASK-DB-006 | [done] | Embedding 语义重排（可选） | CAP-DB-003 `core/database/schema_linking.py` + `schema.py` + `config/settings.py` | `rerank_with_embeddings` 关键词分+embed 相似度加权；`schema_embed_enabled`（默认关）零行为变化、失败静默回退关键词 |

## 3. SQL 安全（TASK-SEC-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-SEC-001 | [done] | SQL 多层校验 | CAP-SEC-001 `sql_validator.py` | AST / 关键字·危险函数黑名单 / 注入检测 / 多语句攻击均拦截 |
| TASK-SEC-002 | [done] | SQL 清理 + 自动 LIMIT | CAP-SEC-002 `sql_sanitizer.py` | 规范化、危险注释移除、LIMIT 钳制到 `sql_max_rows` |
| TASK-SEC-003 | [done] | 风险三态评估 | CAP-SEC-003 `risk_assessor.py` | CRITICAL→DENY / HIGH·MEDIUM→CONFIRM / LOW→ALLOW |
| TASK-SEC-004 | [done] | 敏感表识别 + 中文回述 | CAP-SEC-004 `sql_to_natural_language.py` | HITL 展示用自然语言描述命中表/风险 |
| TASK-SEC-005 | [done] | SQL 错误自纠 | CAP-SEC-005 `sql_error.py` | 13 类错误分类 + SQLSTATE + 修复建议，回喂 LLM 重试 |
| TASK-SEC-006 | [done] | 写操作默认不放行 | CAP-SEC-006 | `enable_sql_write=False` 时写 SQL 校验失败 |
| TASK-SEC-007 | [done] | 任意代码执行默认关 | CAP-SEC-007 `tools/__init__.py` | `create_custom_chart` 仅 `enable_custom_chart=True` 才进工具集 |
| TASK-SEC-008 | [done] | 写操作受边界保护 | CAP-SEC-008 `tools/sql_tools.py` | query_database 分派 INSERT/UPDATE/DELETE→返回受影响行数、写后清 schema 缓存、不入 result_store；DELETE/UPDATE 无 WHERE 仍 DENY；带 `RETURNING` 走 fetch 回显写入行、VALUES 多行为单条批量 |
| TASK-SEC-009 | [done] | 确定性意图路由器 | CAP-SEC-009 `core/security/intent_guard.py` | NL 分类 query/chart/info/malicious/smalltalk/ambiguous/out_of_scope，deny/clarify 语义；`ENABLE_INTENT_ROUTER` 默认关、仅评测直调未接线 |
| TASK-SEC-010 | [done] | 请求准入门 + 注意力经济 | CAP-SEC-010 `core/security/admission.py` + `api/routes.py` | 来源×意图准入判定（admit/deny/clarify/reply）；`maybe_gate` 接线 `/query`（`enable_admission_gate` 默认关、只短路 deny/reply）；allowlist 校验 `X-Admission-Key`；寒暄/INFO 固定直答 |
| TASK-SEC-011 | [done] | 注入检测加固（恒真假布尔） | CAP-SEC-011 `core/security/sql_validator.py` | 两侧均字面量比较（数字=数字/串=串）拒绝；`列='值'`/`列>数字` 不误杀；收 `eval/badcases.md` 待办 |
| TASK-SEC-012 | [done] | 表/列级 RBAC 最小授权 | CAP-SEC-012 `core/security/rbac.py` + `tools/boundaries.py` | 角色解析（`rbac_policy_json`）；系统表→角色表/列 additive checker；越权表/列拒绝、系统表仍拒、列解析失败 fail-closed；`enable_rbac` 默认关零变化 |
| TASK-SEC-013 | [done] | 滑动窗口限流/配额 | CAP-SEC-013 `core/security/rate_limit.py` + `api/main.py` | `parse_rate_limit` 解析 `"N/min"`；限下放行/超限 429/窗口滑动/per-key 隔离/key 上限；`rbac_rate_limit` 默认关 no-op |

## 4. 工具层与权限边界（TASK-TOOL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-TOOL-001 | [done] | SQL 只读工具集 | CAP-TOOL-001 `sql_tools.py` | query_database / list_tables / get_table_schema / get_sample_data / get_relevant_schemas |
| TASK-TOOL-002 | [done] | 统一查询守卫 | CAP-TOOL-002 `boundaries.guard_query_sql` | 校验 + 系统表拒绝 + 表白名单 + LIMIT + 三态门禁 |
| TASK-TOOL-003 | [done] | 统一返回模型 | CAP-TOOL-003 `result_schemas.py` | `QueryResult` 等 Pydantic；`dump_result`/`parse_tool_result` 可用 |
| TASK-TOOL-004 | [done] | 声明式图表 | CAP-TOOL-004 `chart_tools.py` + `chart_spec.py` | 按 result_id 取数 → option_id；字段缺失精确报错、图型自动推荐 |
| TASK-TOOL-005 | [done] | 自定义绘图门控 | CAP-TOOL-005 | 线程池 + 沙箱兜住死循环，默认不暴露 |
| TASK-TOOL-006 | [done] | 分析 / 导出工具 | CAP-TOOL-006 `analysis_tools.py` | statistical_summary / data_profile / export_result（写文件需更高权限） |
| TASK-TOOL-007 | [done] | 长期记忆工具 | CAP-TOOL-007 `memory_tools.py` | remember / recall，由 `enable_memory_tools` 控制 |
| TASK-TOOL-008 | [done] | 工具级权限子集 | CAP-TOOL-008 `tools/__init__.py` | full / read_only / query_only；未知 scope 回退 full |
| TASK-TOOL-009 | [done] | 系统表黑名单同源 | CAP-TOOL-009 `boundaries.SYSTEM_TABLES` | 与 `schema.py` 同源一致；禁止查询 checkpoint/store 表 |

## 5. Agent 与中间件（TASK-AGENT-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-AGENT-001 | [done] | sync/async 双版本 agent | CAP-AGENT-001 `agent/` | 能力一致；async 用 AsyncPostgresSaver 持久化短期记忆 |
| TASK-AGENT-002 | [done] | 系统提示词工作流 | CAP-AGENT-002 `prompts.py` | 先 get_relevant_schemas 再执行；图表先查取 result_id；不臆造表/列；SQL 自纠 |
| TASK-AGENT-003 | [done] | 载荷裁剪中间件 | CAP-AGENT-003 | 跨轮压缩 ToolMessage（condense_tool_results） |
| TASK-AGENT-004 | [done] | 长上下文自动摘要 | CAP-AGENT-004 | token 预算触发（SummarizationMiddleware） |
| TASK-AGENT-005 | [done] | 瞬时错误自动重试 | CAP-AGENT-005 `middleware/config.py` | ToolRetryMiddleware + `sql_retry_on_transient` |
| TASK-AGENT-006 | [done] | 错误结构化格式化 | CAP-AGENT-006 | 工具异常封装为 ToolError，不裸 str(e) 回喂 |
| TASK-AGENT-007 | [done] | 提示词缓存省计费 | CAP-AGENT-007 `agent/prompt_cache.py` + `prompts.py` + `analyst_agent.py` | `prompt_cache_enabled` 时固定段尾 marker + 动态段置尾；off 逐字节不变；`prompt_cache_header_json` 注入 extra_body |
| TASK-MID-001 | [done] | 本地日志中间件 | CAP-MID-001 | logging_middleware |
| TASK-MID-002 | [done] | HITL 中断配置 | CAP-MID-002 | query_database 需审核；只读工具自动放行 |
| TASK-MID-003 | [done] | Checkpointer 高可用 | CAP-MID-003 | AsyncPostgresSaver 优先，失败回退 InMemory |
| TASK-MID-004 | [done] | 长期记忆 Store 静默降级 | CAP-MID-004 | AsyncPostgresStore 失败降级（记忆为加分项） |

## 6. API 与前端（TASK-API-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-API-001 | [done] | 核心端点与契约 | CAP-API-001 `api/routes.py` | query/approve/state/export/chart/health/logs/stream/checkpoints 端点齐备；契约见 `api-spec.yaml` |
| TASK-API-002 | [done] | Bearer Token 鉴权 | CAP-API-002 `api/main.py` | `API_AUTH_TOKEN` 非空时全 `/api/**` 需鉴权；恒定时间比较 |
| TASK-API-003 | [done] | CORS 安全 | CAP-API-003 | `cors_origins` 读取；`*` 时禁 credentials |
| TASK-API-004 | [done] | Web 前端 | CAP-API-004 `static/index.html` | 查询交互 + 会话管理 + ECharts 矢量渲染 + HITL 审批界面 |
| TASK-API-005 | [done] | 查询结果提取 | CAP-API-005 | /query 返回最后成功结果的 columns/data/markdown |
| TASK-API-006 | [done] | 可观测端点 | CAP-API-006 `api/routes.py` | `GET /api/stats`：连接池/线程池/结果缓存状态 |
| TASK-API-007 | [done] | checkpoint 维护端点 | CAP-API-007 `api/routes.py` | /api/checkpoints/stats、cleanup（dry_run 默认开）、cleanup-orphaned |
| TASK-API-008 | [done] | 可观测 /metrics | CAP-API-008 + CAP-OBS-001 `api/routes.py` + `api/main.py` + `observability/` | `observability_enabled` 时 `GET /api/metrics` 返回 Prometheus 文本（工具/请求/连接池 gauge），否则 404；请求计数/延迟中间件门控 |

## 7. Utils（TASK-UTIL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-UTIL-001 | [done] | 结果引用缓存有界 | CAP-UTIL-001 `utils/result_store.py` | 上限 50 条 / 10 分钟过期（代理到 `BoundedTTLCache`） |
| TASK-UTIL-002 | [done] | ECharts option 构建器 | CAP-UTIL-002 `utils/chart_spec.py` | dataset + encode；字段缺失精确报错 |
| TASK-UTIL-003 | [done] | 导出管理 | CAP-UTIL-003 `export_manager.py` | CSV/XLSX；`export_max_rows` 采样上限 |
| TASK-UTIL-004 | [done] | 图表沙箱 + checkpoint 清理 | CAP-UTIL-004 | 安全 globals 沙箱；checkpoint_cleanup 可用 |
| TASK-UTIL-005 | [done] | 并发压测工具 | CAP-UTIL-005 `bench/loadtest.py` | health/ping/query、thread-mode、--dry-run、Bearer 鉴权 |
| TASK-UTIL-006 | [done] | 单一写者缓存原语 | CAP-UTIL-006 `utils/bounded_cache.py` | `BoundedTTLCache`（写/淘汰集中于一个类、读非摧毁式）；Chart 读路径去 `.pop()`；`docs/state-owners.md` 记录各状态唯一写者；消除 result_store/图表 spec 重复实现 |
| TASK-UTIL-007 | [done] | 持久化效果队列 + 指数退避 | CAP-UTIL-007 `utils/effect_queue.py` + `tools/sql_tools.py` | `AsyncEffectQueue`（key 幂等入队、指数退避、可选 JSONL 持久化、pending/settled/failed）；`run_sql_durable` 接通 SQL 瞬时错误退避层（`effect_queue_max_retries` 默认 2） |
| TASK-UTIL-008 | [done] | 缓存后端抽象 memory/Redis | CAP-UTIL-008 `utils/cache_backend.py` | `CacheBackend` Protocol 七方法与 `BoundedTTLCache` 同构；Redis 后端（`run_coroutine_threadsafe` 桥、JSON datetime/Decimal、ZSET 容量淘汰、命名空间前缀）；redis 不可达回退 memory；result_store/chart 签名不变 |

## 8. 评测与测试（TASK-EVAL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-EVAL-001 | [done] | Text2SQL 回归评测 | CAP-EVAL-001 `eval/run_eval.py` | 多场景聚合 harness，跑分类语料 |
| TASK-EVAL-002 | [done] | 分类语料基线 | CAP-EVAL-002 `eval/cases/` | schema_linking(11)/security_deny(13)/routing_guard(17) 三文件 41 例；`mine_badcases.py` 扫日志 dump + `--sink-security` 自动沉淀坏 case |
| TASK-EVAL-003 | [done] | 单元测试覆盖 | CAP-EVAL-003 `tests/` | 安全校验/工具边界/载荷裁剪/返回结构/SQL 错误/图表 spec/写操作/意图路由/评测回归/并发/模型视图重建/准入门/单一写者/效果队列/注入加固/写 RETURNING/语义重排/坏case沉淀/提示词缓存/缓存后端/可观测/RBAC/限流（246 项通过） |
| TASK-EVAL-004 | [done] | 测试硬门槛 | CAP-EVAL-004 | `pytest tests/ -q` 全绿为改动门槛 |
| TASK-EVAL-005 | [done] | 坏 case 自动沉淀 | CAP-EVAL-005 `eval/mine_badcases.py` | `--sink-security [--apply]` 把被安全层拒绝的 query_database 失败按归一 SQL 去重写进 security_deny.json（默认 dry-run、幂等） |

## 9. 可观测（recon）（TASK-RECON-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-RECON-001 | [done] | 模型视图可重建不变量（M1） | CAP-RECON-001/002 `core/recon.py` + `middleware/logging_wrapper.py` + `config/settings.py` | 重建纯函数可用；工具日志记录真实 thread_id + model_view（同 condense 阈值）；断言回归见 `tests/test_recon.py`（10 例）。change：`openspec/archived/recon-model-view-invariant/` |

---

## 候选 / backlog（`[todo]`，未实装）

> 对齐 `specs/spec.md` 状态表备注；**新改动先建 change，合入归档时在此关掉对应 `[todo]`**，保持单一来源（见 `agreement.md` §6）。
> **优先级口径**：`P0` 必做/近期（高价值·低成本或强需求） · `P1` 值得做/中期（明确收益，需排期） · `P2` 可选/远期（锦上添花或依赖前置，成本高）。
> 摘要表 + 每项详情；详情含**成本 / 收益 / 关联 CAP**。

### 摘要

> 注：本 backlog 的 B005/B006/B007/B010 四项已在一次 change 中全部落地，详见「已落地」。

### 已落地（backlog 移出项）

- `export_result` 接入统一 SQL 守卫（原 TASK-BACKLOG-004，[done]）：`tools/analysis_tools.py` 改用 `guard_query_sql`，测试 `test_export_result_rejects_system_table_without_db`；change 见 `openspec/archived/export-result-guard/`。backlog 恒为 `[todo]`，done 项仅在正文 TASK 表记录。
- 同步 agent 补消息裁剪中间件（原 TASK-BACKLOG-002，[done]）：同步版 `create_agent`（`agent/analyst_agent.py`）已与异步版一致追加 `condense_tool_results_middleware` 与 `SummarizationMiddleware`，本 backlog 项实际已实现，归档移出。
- 意图路由器接线 `/query`（原 TASK-BACKLOG-004，[done]）：`core/security/intent_guard.py` 新增 `maybe_short_circuit` 纯函数，`api/routes.py` `/query` 前置接线；受 `ENABLE_INTENT_ROUTER`（默认关）门控、只短路 deny 不短路 clarify（保守低误杀）；测试 `tests/test_intent_router_wiring.py`（7 例）。change 见 `openspec/archived/intent-router-wiring/`。
- 请求准入门 + 注意力经济（原 TASK-BACKLOG-010 准入部分，[done]）：`core/security/admission.py` 的 `AdmissionGate.maybe_gate` 接线 `/query`（CAP-SEC-010）；allowlist 来源准入 + 寒暄/INFO 直答；change 见 `openspec/archived/admission-gate-attention/`。
- 单一写者纪律（[done]）：`utils/bounded_cache.py` `BoundedTTLCache` 收敛两处重复缓存 + 读路径非摧毁式；`docs/state-owners.md`（CAP-UTIL-006）；change 见 `openspec/archived/single-writer-discipline/`。
- 少设置审计（[done]）：删除 `db_max_overflow`/`cache_ttl`/`redis_url`/`agent_verbose` 四个无消费方配置；change 见 `openspec/archived/few-settings-audit/`。
- 持久化效果队列 + 指数退避（[done]）：`utils/effect_queue.py` `AsyncEffectQueue` + `run_sql_durable` 接通 SQL 瞬时错误退避层（CAP-UTIL-007）；change 见 `openspec/archived/durable-effect-queue/`。
- 注入检测加固 + 坏 case 自动沉淀（原 TASK-BACKLOG-009，[done]）：`sql_validator.py` 恒真/恒假字面比较拦截（CAP-SEC-011）+ `mine_badcases --sink-security`（CAP-EVAL-005）；change 见 `openspec/archived/injection-defense-hardening/`。
- 写操作 RETURNING/批量（原 TASK-BACKLOG-008，[done]）：写分派支持 `RETURNING` 回看写入行 + VALUES 多行批量（CAP-SEC-008 增强；多语句事务有意不做）；change 见 `openspec/archived/write-operations-enhanced/`。
- Embedding schema 语义重排（原 TASK-BACKLOG-001，[done]）：`rerank_with_embeddings` 关键词分+embed 相似度加权，`schema_embed_enabled` 默认关零变化（CAP-DB-003 增强）；change 见 `openspec/archived/embedding-schema-retrieval/`。
- 评测语料扩集（原 TASK-BACKLOG-003，[done]）：`eval/cases/` 扩至 41 例（CAP-EVAL-002）；change 见 `openspec/archived/eval-corpus-expansion/`。
- LLM 提示词缓存省计费（原 TASK-BACKLOG-005，[done]）：`agent/prompt_cache.py` + `prompts.py`，固定前置+动态置尾命中 provider 自动磁盘缓存（CAP-AGENT-007）；change 见 `openspec/archived/backlog-quad-cache-rbac-obs/`。
- 多 worker + Redis 共享缓存（原 TASK-BACKLOG-006，[done]）：`utils/cache_backend.py` 后端抽象 memory/Redis（CAP-UTIL-008）；change 见 `openspec/archived/backlog-quad-cache-rbac-obs/`。
- 可观测 /metrics（原 TASK-BACKLOG-007，[done]）：`observability/` 纯 stdlib Prometheus 文本 + `GET /api/metrics`（CAP-OBS-001 / CAP-API-008）；change 见 `openspec/archived/backlog-quad-cache-rbac-obs/`。
- 表/列级 RBAC + 速率限制（原 TASK-BACKLOG-010，[done]）：`core/security/rbac.py` + `rate_limit.py`（CAP-SEC-012/013）；change 见 `openspec/archived/backlog-quad-cache-rbac-obs/`。

---

*版本：v0.5（对齐 backlog 四强补齐：提示词缓存/Redis 共享缓存/可观测 metrics/RBAC+限流；backlog B005/B006/B007/B010 均 `[done]`） | 更新：2026-11-09*