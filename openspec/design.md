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

## 4. 数据契约（Contracts）

> 关键数据结构 / 返回模型。当前以 Pydantic 模型 + 统一序列化表示（见 `tools/result_schemas.py`）。
> 需 Q&A 或后续补充明确的契约清单。

- QueryResult（columns / data / markdown 表格）
- create_chart → option_id；结果引用 → result_id

## 5. 开放问题 / 候选演进

- `get_relevant_schemas` 改 Embedding 语义检索
- 同步版 agent 补消息裁剪中间件
- Golden 测试集扩展召回 / 关联 / 安全边界 case

---

*版本：v0.1（基于现有代码基线） | 更新：2026-10-07*