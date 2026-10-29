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
| TASK-SEC-008 | [done] | 写操作受边界保护 | CAP-SEC-008 `tools/sql_tools.py` | query_database 分派 INSERT/UPDATE/DELETE→返回受影响行数、写后清 schema 缓存、不入 result_store；DELETE/UPDATE 无 WHERE 仍 DENY |
| TASK-SEC-009 | [done] | 确定性意图路由器 | CAP-SEC-009 `core/security/intent_guard.py` | NL 分类 query/chart/info/malicious/smalltalk/ambiguous/out_of_scope，deny/clarify 语义；`ENABLE_INTENT_ROUTER` 默认关、仅评测直调未接线 |

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

## 7. Utils（TASK-UTIL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-UTIL-001 | [done] | 结果引用缓存有界 | CAP-UTIL-001 `utils/result_store.py` | 上限 50 条 / 10 分钟过期 |
| TASK-UTIL-002 | [done] | ECharts option 构建器 | CAP-UTIL-002 `utils/chart_spec.py` | dataset + encode；字段缺失精确报错 |
| TASK-UTIL-003 | [done] | 导出管理 | CAP-UTIL-003 `export_manager.py` | CSV/XLSX；`export_max_rows` 采样上限 |
| TASK-UTIL-004 | [done] | 图表沙箱 + checkpoint 清理 | CAP-UTIL-004 | 安全 globals 沙箱；checkpoint_cleanup 可用 |
| TASK-UTIL-005 | [done] | 并发压测工具 | CAP-UTIL-005 `bench/loadtest.py` | health/ping/query、thread-mode、--dry-run、Bearer 鉴权 |

## 8. 评测与测试（TASK-EVAL-*）

| ID | 状态 | 任务 | 范围（CAP / 文件） | 验收要点 |
|----|------|------|--------------------|----------|
| TASK-EVAL-001 | [done] | Text2SQL 回归评测 | CAP-EVAL-001 `eval/run_eval.py` | 多场景聚合 harness，跑分类语料 |
| TASK-EVAL-002 | [done] | 分类语料基线 | CAP-EVAL-002 `eval/cases/` | schema_linking/security_deny/routing_guard 三文件；`mine_badcases.py` 扫日志 dump 坏 case |
| TASK-EVAL-003 | [done] | 单元测试覆盖 | CAP-EVAL-003 `tests/` | 安全校验/工具边界/载荷裁剪/返回结构/SQL 错误/图表 spec/写操作/意图路由/评测回归/并发（121 项） |
| TASK-EVAL-004 | [done] | 测试硬门槛 | CAP-EVAL-004 | `pytest tests/ -q` 全绿为改动门槛 |

---

## 候选 / backlog（`[todo]`，未实装）

> 对齐 `specs/spec.md` 状态表备注；**新改动先建 change，合入归档时在此关掉对应 `[todo]`**，保持单一来源（见 `agreement.md` §6）。
> **优先级口径**：`P0` 必做/近期（高价值·低成本或强需求） · `P1` 值得做/中期（明确收益，需排期） · `P2` 可选/远期（锦上添花或依赖前置，成本高）。
> 摘要表 + 每项详情；详情含**成本 / 收益 / 关联 CAP**。

### 摘要

| ID | 优先级 | 候选任务 | 核心动机 | 落点 |
|----|--------|----------|----------|------|
| B001 | P1 | Embedding schema 语义检索 | `get_relevant_schemas` 硬编码关键词映射，表多召回不稳 | `core/database/schema_linking.py` |
| B002 | P1 | 同步 agent 补消息裁剪中间件 | 与异步版能力对齐，防长对话 token 超限 | `agent/` |
| B003 | P2 | 评测语料扩集（召回/关联/边界） | 用例较少、回归覆盖不足 | `eval/cases/*` |
| B004 | P1 | 意图路由器接线 `/query` 前置拒答/澄清 | `intent_guard` 已实现未用，运行时仍裸走 LLM | `api/routes.py` + `core/security/intent_guard.py` |
| B005 | P0 | LLM 提示词缓存省计费 | 相同系统提示词每次全量计费 | `middleware/` / LLM 侧缓存 |
| B006 | P2 | 多 worker + Redis 共享缓存 | 单 worker 内存缓存跨进程 miss（result_store/chart） | `utils/` / `config/settings.py` |
| B007 | P1 | 可观测: OpenTelemetry metrics/追踪 | 缺统一指标与链路追踪，压测定界难 | 新增 `observability/` + `GET /metrics` |
| B008 | P2 | 写操作增强:RETURNING/批量/事务 | 写后只能见行数，无法回看写入数据 | `tools/sql_tools.py` |
| B009 | P1 | 更严注入检测 + 坏 case 自动扩集 | 恒真注入 `OR '1'='1'` 等在 SQL 层不拦 | `core/security/` + `eval/mine_badcases.py` |
| B010 | P2 | 表/列级 RBAC + 速率限制/配额 | 仅有登录鉴权，无最小授权/防滥用 | `api/` + `tools/boundaries.py` |

### 详情

**TASK-BACKLOG-001 · Embedding schema 语义检索（P1）**
- 动机：`get_relevant_schemas` 仍基于硬编码关键词/同义词映射，表多或措辞新时召回不稳。
- 落点：`core/database/schema_linking.py`（接入 embedding 模型对表/列注释做向量召回，关键词作回退）。
- 成本：中（引入 embedding 依赖/向量存储 + 评测调参）。
- 收益：召回精度提升 → 减少 LLM 错表/错列与重试。
- 关联：CAP-DB-003 / CAP-AGENT-002。

**TASK-BACKLOG-002 · 同步 agent 补消息裁剪中间件（P1）**
- 动机：同步版 `create_agent` 缺跨轮 ToolMessage 裁剪，长对话可能 token 超限（与异步版不一致）。
- 落点：`agent/`（复用异步版 `condense_tool_results` 中间件）。
- 成本：低（复用既有中间件）。
- 收益：两版能力对齐，防同步版长对话超预算。
- 关联：CAP-AGENT-003 / CAP-AGENT-001。

**TASK-BACKLOG-003 · 评测语料扩集（P2）**
- 动机：`eval/cases/` 分类用例仍较少，召回/关联/安全边界覆盖不足。
- 落点：`eval/cases/schema_linking.json` / `security_deny.json` / `routing_guard.json` 扩充。
- 成本：低-中（造语料 + 定金标准则）。
- 收益：回归更稳，防退化。
- 关联：CAP-EVAL-001/002/003。

**TASK-BACKLOG-004 · 意图路由器接线 `/query` 前置拒答/澄清（P1）**
- 动机：`intent_guard` 已实现且确定性可测，但 `ENABLE_INTENT_ROUTER` 默认关、仅评测直调；运行时仍全量进 LLM，恶意/闲聊/歧义无前置拦截。
- 落点：`api/routes.py`（`/query` 入口按开关走 intent_guard，命中 malicious 拒答、ambiguous/smalltalk 澄清复用 LLM）。
- 成本：中（改路由入口，需评估对既有 `/query` 行为/测试影响；默认仍需配置开关）。
- 收益：恶意/离题请求前置拦截，省 LLM 成本、减少误答与风险面。
- 关联：CAP-SEC-009 / CAP-AGENT-002。

**TASK-BACKLOG-005 · LLM 提示词缓存省计费（P0）**
- 动机：系统提示词（长、多段）每请求/每轮全量计费，可缓存命中省钱。
- 落点：`middleware/`（对系统提示词/固定段启用 provider prompt 缓存，如 Anthropic cache_control），或 LLM 侧缓存。
- 成本：低（适配供应商缓存机制，需校验基准提示词稳定）。
- 收益：相同提示词重复调用计费下降显著。
- 关联：CAP-CONF-004 / CAP-AGENT-002。

**TASK-BACKLOG-006 · 多 worker + Redis 共享缓存（P2）**
- 动机：单 worker 默认安全，但扩 worker 后 result_store/chart 缓存为每进程内存，`/query` 的 result_id 与 `/chart/option` 取图跨 worker 会 404。
- 落点：`utils/result_store.py` / `tools/chart_tools.py` 缓存后端改 `redis_url`（已预留配置）；checkpointer/store 已走 PG 天然可跨。
- 成本：高（引入 Redis 依赖 + 缓存语义改造 + 并发一致性测试）。
- 收益：横向扩并发、多 worker 可用。
- 关联：CAP-UTIL-001 / CAP-UTIL-002 / CAP-API-006。

**TASK-BACKLOG-007 · 可观测: OpenTelemetry metrics/追踪（P1）**
- 动机：缺统一指标与分布式追踪，压测/生产定位慢 LLM/慢查询缺少链路证据。
- 落点：新增 `observability/`（OTel traces + `/metrics` 暴露连接池/工具耗时/错误率，承接 `/api/stats`）。
- 成本：中（OTel 集成 + 埋点 + 看板）。
- 收益：性能瓶颈与错误可视化，支撑压测闭环与生产排障。
- 关联：CAP-API-006 / CAP-MID-001。

**TASK-BACKLOG-008 · 写操作增强: RETURNING/批量/事务（P2）**
- 动机：写操作目前只返回受影响行数，用户看不到写入后的真实数据；无批量/事务编排。
- 落点：`tools/sql_tools.py`（写分派支持 RETURNING 回传、可选事务包裹多语句）。
- 成本：中（SQL 改写 + 返回结构扩展 + 边界收紧）。
- 收益：写后可直接回看、支持批量操作，工程/业务价值更高。
- 关联：CAP-SEC-008 / CAP-TOOL-003。

**TASK-BACKLOG-009 · 更严注入检测 + 坏 case 自动扩集（P1）**
- 动机：恒真注入 `OR '1'='1'`、布尔盲注等当前在 SQL 层不拦（`badcases.md` 待办）；坏 case 需人工沉淀。
- 落点：`core/security/sql_validator.py` / `sql_sanitizer.py` 补 pattern；`eval/mine_badcases.py` 全自动把失败调用沉淀成 `security_deny.json` 用例。
- 成本：中（扩展校验 + 自动沉淀管道）。
- 收益：注入防线更密、坏 case 持续自我补强。
- 关联：CAP-SEC-001/002 / CAP-EVAL-002。

**TASK-BACKLOG-010 · 表/列级 RBAC + 速率限制/配额（P2）**
- 动机：现有仅 `API_AUTH_TOKEN` 登录鉴权 + 工具级 scope，无最小表/列授权与滥用防护。
- 落点：`tools/boundaries.py` 表白名单按角色；`api/` 加速率限制/配额（配合鉴权）。
- 成本：高（认证扩为多用户、策略存储、限流中间件）。
- 收益：多租户/多角色可控、防爬与配额治理，贴近生产安全基线。
- 关联：CAP-TOOL-008 / CAP-API-002。

### 已落地（backlog 移出项）

- `export_result` 接入统一 SQL 守卫（原 TASK-BACKLOG-004，[done]）：`tools/analysis_tools.py` 改用 `guard_query_sql`，测试 `test_export_result_rejects_system_table_without_db`；change 见 `openspec/archived/export-result-guard/`。backlog 恒为 `[todo]`，done 项仅在正文 TASK 表记录。

---

*版本：v0.2（对齐代码基线：写操作/意图路由/压测/可观测 + backlog 扩为带优先级路线） | 更新：2026-10-29*