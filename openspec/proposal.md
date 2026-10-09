# 项目提案（Project Proposal）

> 项目级 RD 文档，给**人** review 用，回答「这个项目做什么、怎么做、如何验收」。
> 编号规则：`PROP-xxx`。本文档是活文档，随 Q&A 填充、随改动演进。
> 对照参考：sdd-in-action `book-code/specs/proposal.md`（背景与目标 → 功能范围 → 验收标准 → 术语）。
>
> **填充说明**：§1.2 / 1.3 / 2.x / 3.x 由既有文档（`spec.md` 能力基线、`design.md`、`project.md`、`agreement.md` §3/§5）与 §1.1 三目标整理回填，而非实时 Q&A；后续 Q&A 可在此基础上增删。

---

## 1. 背景与目标（Background & Goals）

### 1.1 背景

数据库里存了大量有价值的数据，但**只有会写 SQL 的技术人员能直接查询**。业务用户（市场、运营、销售等非技术角色）想拿一个数，常常要排队等研发提数，沟通成本高、反馈慢，想看的多角度分析（趋势、分布、对比）更难实现。

正是这个「数据明明在库里，非技术的人却够不着」的痛点，催生了本项目。**不这么做会怎样**：数据持续沉淀却难被业务真正用起来，决策依赖研发逐个提数，数据的价值被技术门槛拦在门外。

本项目要解决三件事：
1. **降低门槛**——让非技术用户用自然语言（中文）就能查数据库，不需要懂 SQL。
2. **提升可观测性**——查询结果清晰、可解释，用户能看懂数从哪来、意味着什么。
3. **多角度可视化**——用图表等可视化形式，从趋势、分布、对比等多个角度呈现数据内容。

### 1.2 目标

可验证的期望结果是三产品目标 + 工程目标。已完成能力（现状基线）详见 `openspec/specs/spec.md` 的 CAP-xxx，不再重复罗列，此处只写**达成形态**：

1. **门槛降到自然语言**：非技术用户经 Web UI 输入中文即可触发查询，拿到 Markdown 结果表 + 声明式图表，全程不接触 SQL（基线 CAP-AGENT-002 / CAP-API-001 / CAP-TOOL-004）。
2. **结果可解释**：每次查询有结构化结果（columns/data/Markdown 表），会话内可回看所用 SQL；schema linking 命中带理由，避免「黑盒出数」（基线 CAP-API-005 / CAP-DB-003 / CAP-SEC-004）。
3. **可视化多角度**：bar(对比)/line(趋势)/pie(分布)/scatter(相关) 四种图型，缺省按数据特征自动推荐，字段缺失精确报错（基线 CAP-TOOL-004 / CAP-UTIL-002）。
4. **工程目标**（见 `project.md` Goals）：安全第一、正确性、低成本、可用性——作为贯穿性验收约束。

### 1.3 目标用户

- **业务用户（市场 / 运营 / 销售等非技术）**：用 Web 前端提问、看结果与图表。诉求：免写 SQL、结果一眼看懂、图表能多角度切。
- **研发 / 数据负责人**：通过 API 与配置接入、处理 HITL 审批、从审计日志追溯。诉求：可控、可审计、不越权执行。
- **评估 / 维护者（AI / 工程）**：靠 `eval/golden_queries.json` 回归 + `tests/` 单测保障不回归。诉求：改动可自动验证。

## 2. 功能范围（Functional Scope）

### 2.1 做什么（In scope）

按 `openspec/specs/spec.md` 能力基线分组，本期交付的核心能力：

- **Text2SQL 查询闭环**：理解自然语言意图 → schema linking 回召真实表结构 → 生成并校验 SQL → 执行 → 返回结构化结果 / 图表（CAP-DB-003 / CAP-AGENT-002）。
- **SQL 安全**：多层校验（AST / 关键字·危险函数黑名单 / 注入 / 多语句）、清理 + 自动 LIMIT、风险三态 ALLOW/CONFIRM/DENY、HITL 人工审批（CAP-SEC-001..007）。
- **工具层**：只读 SQL 工具集、声明式图表 `create_chart`、自定义绘图 `create_custom_chart`（默认关闭）、分析工具、长期记忆工具、权限子集 full/read_only/query_only（CAP-TOOL-001..009）。
- **记忆**：同 thread 多轮短期记忆（checkpointer）+ 跨会话长期记忆（store，remember/recall）（CAP-MID-003/004 / CAP-AGENT-001）。
- **API + Web 前端**：查询 / HITL 审批 / 会话状态 / 导出 / 图表 option / 流式 / 健康检查 / 日志 / checkpoint 清理；ECharts 矢量渲染 + 审批界面（CAP-API-001..005）。
- **可观测性与成本**：载荷裁剪、长上下文自动摘要、本地日志、HITL 审计（CAP-MID / CAP-UTIL）。
- **评测与回归**：Text2SQL golden 集评测 + 单元测试硬门槛（CAP-EVAL-001..004）。

### 2.2 不做什么（Non-goals，明确排除）

> 防范围蔓延。沿用 `project.md` Scope & Non-goals：

- 不连接多数据源 / 异构数据库（仅 PostgreSQL）。
- 不做跨 Agent 编排 / 多角色协作。
- 不提供用户管理、租户隔离等平台化能力（属外部系统）。
- 不做训练数据生成 / 多轮自我进化。
- 不内置业务库的真实 schema（以 `get_relevant_schemas` 运行时返回为准，避免硬编码表名——见 `agreement.md` Avoid#1）。

### 2.3 技术约束

- 技术栈：`Python` + `LangChain / LangGraph (deepagents)` + `FastAPI` + `PostgreSQL/asyncpg`（`agreement.md` §1）。
- 分层铁律：`api → agent → tools → core`，`tools` 不得反向依赖 `api/agent`；配置进 `config/settings.py` 并给默认值，敏感值走 `.env`（`agreement.md` §1 / §4）。
- 运行方式：本地开发 `run_server.py` / `start_windows.py`；API 为单 worker 异步 uvicorn 应用（`config/settings.py`）。
- 安全红线必守：见 `agreement.md` §3（SQL 校验、HITL、任意代码执行默认关、工具边界），违反即打回。

## 3. 验收标准（Acceptance Criteria）

> 对应 §2.1 能力，逐条可验证。*现状 = 已审阅代码时的实现状态，供验收基线，非承诺。*

### 3.1 功能验收

- [ ] 中文提问经 Web UI 触发查询，返回 Markdown 结果表 + 结构化 data（*现状：✅ CAP-API-005*）。
- [ ] 可生成 bar/line/pie/scatter 图表，缺省按数据特征自动推荐，字段缺失精确报错（*现状：✅ CAP-TOOL-004 / CAP-UTIL-002*）。
- [ ] schema linking 返回真实表结构与命中理由，不臆造表/列（*现状：✅ CAP-DB-003 / CAP-AGENT-002*）。
- [ ] 写操作默认拒绝、query_database 走 HITL 人工审批并可续跑/拒绝（*现状：✅ CAP-SEC-006 / CAP-MID-002*）。
- [ ] 同 thread 多轮短期记忆与 remember/recall 长期记忆可用（*现状：✅ CAP-MID-003/004*）。
- [ ] 导出 CSV/XLSX 可经 `/api/export/{file}` 下载（*现状：✅ CAP-UTIL-003*）。
- [ ] 配置 `API_AUTH_TOKEN` 后全 `/api/**` 需 Bearer 鉴权；CORS `*` 时禁用 credentials（*现状：✅ CAP-API-002/003*）。
- [ ] golden 查询回归 + `pytest tests/ -q` 全绿（*现状：✅ 76 项通过*）。

### 3.2 性能 / 成本验收

> 成本控制为既有红线（`agreement.md` §5），映射为可测项。

- [ ] 图表数据引用化：data 按 result_id（≤ ~20 token）引用，不重复回传全量数据（*现状：✅ result_store / chart_tools*）。
- [ ] 工具返回载荷有界：rows/cell/content 三级裁剪上限（*现状：✅ tool_result_max_* 配置*）。
- [ ] schema 召回 ≤ `schema_max_relevant_tables`，避免一次塞进过载上下文（*现状：✅ 默认 3，上下限 1..10*）。
- [ ] 长上下文自动摘要按 `context_budget`（≈0.8×窗口）触发（*现状：✅ CAP-AGENT-004*）。
- [ ] SQL 自动 LIMIT 钳制到 `sql_max_rows`，防全表扫描（*现状：✅ CAP-SEC-002*）。

### 3.3 安全 / 边界验收

> 安全红线见 `agreement.md` §3，逐条映射为可测验收项。

- [ ] 所有 SQL 工具调用过 `core/security` 多层校验 + `RiskAssessor` 风险三态门禁（*现状：✅ CAP-SEC-001/003*）。
- [ ] 写操作 / 高风险查询执行前进 HITL approve/reject，决策写入审计日志（*现状：✅ CAP-MID-002 / audit*）。
- [ ] `enable_sql_write=False` 时写 SQL 校验失败（*现状：✅ CAP-SEC-006*）。
- [ ] `create_custom_chart` 默认不进工具集，仅 `enable_custom_chart=True` 才暴露（*现状：✅ CAP-SEC-007 / CAP-TOOL-005*）。
- [ ] 新工具默认 read-only；权限子集 full/read_only/query_only 生效，未知 scope 回退 full（*现状：✅ CAP-TOOL-008*）。
- [ ] 系统表（checkpoint/store）黑名单同源一致，禁止查询（*现状：✅ CAP-TOOL-009*）。
- [ ] **[已知隐患 / 待改进]** `export_result` 未走统一 `guard_query_sql` 守卫（并行校验路径、未查系统表黑名单）——近期候选收口（`tools/analysis_tools.py:181`）。

## 4. 术语定义（Glossary）

> 术语表维护在独立文件 `openspec/terminology.md`（`TERM-xxx`），本文档在出现歧义处引用，不重复维护。
> 关键口径：Text2SQL、schema linking、HITL、风险三态、result_id、option_id、result_store、checkpointer、store、载荷裁剪、schema_max_relevant_tables、sql_max_rows、golden 集（详见 `openspec/terminology.md`）。

---

*规范版本：v0.2（已由既有文档回填待填充项） | 维护人：@mcx | 更新：2026-10-09*