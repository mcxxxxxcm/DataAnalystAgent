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
| CAP-DB-003 | 相关表召回（schema linking）：按相关性评分排序、上限 `schema_max_relevant_tables`、命中理由 | ✅ `schema_linking.py` |
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

## 8. Utils

| ID | 需求 | 现状 |
|----|------|------|
| CAP-UTIL-001 | 查询结果引用缓存有界 TTL（上限 50 条 / 10 分钟过期） | ✅ `utils/result_store.py` |
| CAP-UTIL-002 | ECharts option 构建器 `build_echarts_option`（dataset + encode，字段缺失精确报错） | ✅ `utils/chart_spec.py` |
| CAP-UTIL-003 | 导出管理 export_manager（CSV/XLSX，`export_max_rows` 采样上限） | ✅ |
| CAP-UTIL-004 | 图表代码沙箱 `execute_chart_code`（安全 globals，非危险） + checkpoint 清理 | ✅ `chart_sandbox.py` / `checkpoint_cleanup.py` |

## 9. Eval & Tests

| ID | 需求 | 现状 |
|----|------|------|
| CAP-EVAL-001 | Text2SQL 回归评测：`eval/run_eval.py` 跑 golden 用例 | ✅ |
| CAP-EVAL-002 | Golden 集覆盖表检索 / 聚合 / 关联 / 写操作拒绝 / 结构检索 5 例 | ✅ `golden_queries.json` |
| CAP-EVAL-003 | 单元测试：安全校验 / 工具边界 / 载荷裁剪 / 返回结构 / SQL 错误 / 图表 spec | ✅ `tests/`（76 项通过） |
| CAP-EVAL-004 | `pytest tests/ -q` 为改动硬门槛 | ✅ |

---

## Specs 状态表

| 能力域 | 状态 | 备注（候选/风险） |
|--------|------|-------------------|
| Configuration | implemented | — |
| core/database | implemented | `get_relevant_schemas` 仍基于硬编码关键词映射，候选改 Embedding 语义检索（agreement 未实装项） |
| core/security | implemented | — |
| Tools | implemented | `create_custom_chart` 默认禁用（安全设计）；同步版 agent 缺消息裁剪中间件（见 agreement 候选） |
| Agent | implemented | — |
| Middleware | implemented | — |
| API + Frontend | implemented | — |
| Utils | implemented | — |
| Eval & Tests | implemented | Golden 用例较少，可扩展更多召回/关联/安全边界 case |