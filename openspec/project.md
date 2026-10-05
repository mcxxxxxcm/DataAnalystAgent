# Project Overview（项目简介）

> 本文档描述项目存在的原因、边界、目标与分层。英文为结构性关键词，中文为说明，与 `agreement.md` 一致。

## Why（为什么有这个项目）

用户希望用**自然语言**查询数据库并得到结果/图表，而非手写 SQL。本项目把一个 **Text2SQL** Agent 收拢成可用的产品闭环：用户中文提问 → Agent 理解意图 → 检索库的真实表结构 → 生成并**安全校验** SQL → 执行 → 返回结构化结果或声明式图表。

直接的 Text2SQL 有多重真实痛点，本项目逐个回应：

- **幻觉**：LLM 臆造不存在的表/列名 → 强制先取真实 schema，SQL 自纠只依据真实结构。
- **不安全**：写操作、删表、全表扫描 → 多层 SQL 校验 + 风险三态门禁 + HITL。
- **不可信**：执行结果姿势不一 → 工具返回统一 Pydantic 模型 + 结构化载荷。
- **费 token**：图表把完整结果重传进工具参数 → 数据引用化（result_id）+ 载荷裁剪。

## Responsibilities（职责）

本 Agent 负责：

1. 理解中文/自然语言查询意图，映射到相关表结构（schema linking）。
2. 生成 SQL，经安全层校验、清理、自动 LIMIT 后执行。
3. 对写操作 / 高风险查询进入人工审核（HITL）后放行。
4. 返回结构化结果（含引用 id、Markdown 表格），按需生成 ECharts 图表。
5. 维持多轮对话短期记忆（checkpointer）与跨会话长期记忆（store）可用的数据口径。
6. 提供工具级权限边界（full / read_only / query_only）与可选 API 鉴权。

## Scope & Non-goals（范围与边界）

**In scope（做）**：单库 PostgreSQL 的 Text2SQL 分析、SQL 安全、HITL、图表、短/长期记忆、工具权限、输入输出结构统一、日志与审计、回归评测。

**Non-goals（明确不做，防范围蔓延）**：

- 不连接多数据源/异构数据库（仅 PostgreSQL）。
- 不做跨 Agent 编排 / 多角色协作。
- 不提供用户管理、租户隔离等平台化能力（属外部系统）。
- 不做训练数据生成 / 多轮自我进化。
- 不内置业务库的真实 schema（以 `get_relevant_schemas` 运行时返回为准，避免硬编码表名进提示词——见 agreement Avoid#1）。

## Goals（目标）

按优先级：

1. **安全第一**：任何工具调用都过安全校验；写操作默认需 HITL；任意代码执行默认关（`create_custom_chart` 门控）；安全红线不可妥协（agreement §3）。
2. **正确性**：不臆造表/列名，SQL 失败自纠（最多重试 3 次），结果 Markdown 表格精度高。
3. **低成本**：图表数据引用化（result_id ≤ ~20 token）、工具返回载荷有界裁剪、schema 召回有上限、长上下文自动摘要。
4. **可用性**：同步/异步 agent 双版本一致，API + Web 前端可交互。

## Layers（分层，改动勿越层）

- `config/` 配置层 —— pydantic-settings，全部带默认值。
- `core/` 核心基础设施 —— **不暴露给 LLM**（db 连接池 / schema / schema linking / security 校验）。
- `tools/` 工具层 —— 暴露给 LLM 的可调用工具；**权限边界在此**（`boundaries.py`）。
- `agent/` —— 创建 agent（sync/async）、系统提示词（prompts）。
- `api/` + `static/` —— FastAPI 后端 + Web 前端（ECharts 渲染）。
- `middleware/` —— 日志 / 载荷裁剪 / 摘要 / HITL / 瞬时错误重试 / store / checkpointer。
- `utils/` —— 结果缓存（有界 TTL）、图表声明式 spec、导出、checkpoint 清理。
- `eval/` + `tests/` —— Text2SQL 回归评测 + 单元测试。

层间依赖方向：`api → agent → tools → core`；`tools` 不得反向依赖 `api/agent`。