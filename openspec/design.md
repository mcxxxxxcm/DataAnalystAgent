# 技术设计（Design）

> 项目级技术设计，给**工程师** review 用，回答「用什么架构、拆哪些模块、关键取舍」。
> 编号规则：`DES-xxx`。基于现有代码基线撰写，随改动演进。
> 对照参考：sdd-in-action `book-code/specs/design.md`。

---

## 1. 总体架构

引用 `openspec/agreement.md` §1 的分层铁律：
`api → agent → tools → core`，`tools` 不得反向依赖 `api/agent`。

- `config/` 配置层（pydantic-settings，全带默认值）
- `core/` 核心基础设施（**不暴露给 LLM**）：db 连接池 / schema / schema linking / security
- `tools/` 工具层（暴露给 LLM，权限边界在此 `boundaries.py`）
- `agent/` 创建 agent（sync/async）+ 系统提示词
- `api/` + `static/` FastAPI 后端 + Web 前端
- `middleware/` 日志 / 载荷裁剪 / 摘要 / HITL / 重试 / store / checkpointer
- `utils/` 结果缓存（有界 TTL）/ 图表 spec / 导出 / checkpoint 清理
- `eval/` + `tests/` 回归评测 + 单元测试

## 2. 模块职责与关键实现

| 模块 | 职责 | 关键实现文件 |
|------|------|--------------|
| 配置 | 集中配置、上下文预算推断 | `config/settings.py` |
| 数据库 | 异步连接池、schema 管理、schema linking | `core/database/*` |
| 安全 | SQL 多层校验、清理、风险三态、错误自纠 | `core/security/*` |
| 工具 | 只读 SQL、图表、分析、长期记忆、权限子集 | `tools/*` |
| Agent | 双版本构建、提示词工作流 | `agent/*` |
| 中间件 | 载荷裁剪、摘要、HITL、重试、store/checkpointer | `middleware/*` |
| API+前端 | 端点、鉴权、CORS、ECharts 渲染 | `api/*` + `static/*` |
| Utils | 结果缓存、图表构建器、导出、沙箱 | `utils/*` |
| 评测 | Text2SQL 回归、golden 用例 | `eval/*` |

> 细节能力清单以 `openspec/specs/spec.md`（CAP-xxx）为准，此处不重复堆叠。

## 3. 关键设计决策（ADR 汇总）

> 单一决策点 → 选了什么 → 理由 / 代价。可在 `openspec/design.md` 内维护，或按 `adrs/` 拆分。

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| schema 召回 | 硬编码关键词映射（候选改 Embedding） | 简单免依赖 | 表多时召回不稳（agreement 候选） |
| 图表数据 | 数据引用化（result_id ≤ ~20 token） | 省 token | 需额外取数步骤 |
| SQL 校验 | AST + 黑名单 + 注入检测 + 自动 LIMIT | 多层兜底 | 安全层为强依赖 |
| 任意代码执行 | 默认关，`create_custom_chart` 门控 | 安全红线 | 能力受限 |
| 缓存 | 内存有界 TTL（50 条 / 10min） | 免外部依赖 | 重启即失效 |
| 记忆 | checkpointer 优先 AsyncPostgresSaver、store 静默降级 | 高可用 | 记忆非强依赖 |
| SQL 守卫 | 所有查询统一走 `guard_query_sql` | 单一安全实现、消灭并行校验路径 | 非守卫查询（export_result）需收口（见 proposal §3.3） |
| 风险决策入口 | HITL 统一挂在 query_database；只读工具自动放行 | 审核聚焦写/高风险，降低噪声 | 中等风险只读查询不额外打扰 |
| 权限模型 | 工具级 scope（full/read_only/query_only） | 按调用方最小授权 | 未知 scope 回退 full 需审慎 |
| API 契约 | 轻量 YAML，非 OpenAPI | 契合项目既有口语化文档风格 | 不与 swagger-ui 等工具直接互操作 |

## 4. 数据契约（Contracts）

> 分两层：**内部工具契约**（`tools/result_schemas.py` 的 Pydantic 模型，供 Agent 工具间传递）
> 与 **对外 API 契约**（`openspec/api-spec.yaml`，请求/响应模型见 `api/schemas.py`）。
> 三层口径对齐，避免同一数据多套姿势；术语见 `openspec/terminology.md`。

### 4.1 内部工具契约（`tools/result_schemas.py`）

| 结构 | 字段 | 说明 |
|------|------|------|
| QueryResult | columns / data / markdown 表格 | 统一序列化表示；`dump_result` / `parse_tool_result` 往返 |
| 引用句柄 | result_id | 查询结果引用 id（≤ ~20 token），图表/后端经缓存取数，代替全量回传 |
| 图表句柄 | option_id | ECharts option 引用 id；`create_chart` 输出 |

### 4.2 对外 API 契约（`openspec/api-spec.yaml`）

- 端点 / 方法 / 参数 / 请求 / 响应 / 鉴权 / CORS / 错误语义 均在 `api-spec.yaml` 定义，与 `api/routes.py` + `api/schemas.py` 对齐。
- 请求/响应 Pydantic 模型清单：QueryRequest / ApprovalRequest / ActionRequest /
  FormattedApprovalRequest / QueryResponse / ApprovalResponse / StateResponse /
  HealthResponse / LogResponse / ErrorResponse。

### 4.3 API 端点一览（索引，详见 `api-spec.yaml`）

| 方法 | 路径 | 契约模型（req → resp） | 能力 |
|------|------|------------------------|------|
| POST | /api/query | QueryRequest → QueryResponse | CAP-API-001/005 |
| POST | /api/approve | ApprovalRequest → ApprovalResponse | CAP-API-001 / CAP-SEC-004 |
| GET  | /api/state/{thread_id} | – → StateResponse | CAP-API-001 / CAP-MID-003 |
| GET  | /api/export/{file_id} | – → 附件 | CAP-API-001 / CAP-UTIL-003 |
| GET  | /api/chart/option/{chart_id} | – → dict（option/PNG） | CAP-API-001 / CAP-TOOL-004 |
| GET  | /api/health | – → HealthResponse | CAP-API-001 |
| GET  | /api/logs | limit/tool_name → LogResponse | CAP-API-001 / CAP-MID-001 |
| GET  | /api/stream/{thread_id}?query= | – → SSE | CAP-API-001 / CAP-AGENT-001 |
| GET  | /api/checkpoints/stats | – → dict | CAP-API-001 / CAP-UTIL-004 |
| POST | /api/checkpoints/cleanup | days_to_keep/dry_run → dict | CAP-API-001 / CAP-UTIL-004 |
| POST | /api/checkpoints/cleanup-orphaned | dry_run → dict | CAP-API-001 / CAP-UTIL-004 |

## 5. 开放问题 / 候选演进

> 候选任务已收敛到 `openspec/tasks.md` 的「候选 / backlog」小节（TASK-BACKLOG-*），此处只保留要点与落点。

- `get_relevant_schemas` 改 Embedding 语义检索（TASK-BACKLOG-001，落点 `core/database/schema_linking.py`）
- 同步版 agent 补消息裁剪中间件（TASK-BACKLOG-002，落点 `agent/`）
- Golden 测试集扩展召回 / 关联 / 安全边界 case（TASK-BACKLOG-003，落点 `eval/golden_queries.json`）
- `export_result` 接入统一 SQL 守卫（TASK-BACKLOG-004，对应 change：`openspec/changes/export-result-guard/`）

---

*版本：v0.2（扩数据契约、补 ADR 与端点索引、候选收敛到 tasks.md） | 更新：2026-10-13*