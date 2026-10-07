# 术语表（Glossary）

> 统一项目口径，避免同一概念多种说法。`proposal.md` / `design.md` / `spec.md` 引用这里。
> 编号规则：`TERM-xxx`。随 Q&A / 演进补充。

| 编号 | 术语 | 定义 | 备注 |
|------|------|------|------|
| TERM-001 | Text2SQL | 自然语言 → SQL 的结构化查询生成 | 项目核心范式 |
| TERM-002 | schema linking | 把用户意图映射到真实库表/列结构 | `core/database/schema_linking.py` |
| TERM-003 | HITL | Human-In-The-Loop，写操作/高风险查询人工审核放行 | 安全红线，agreement §3 |
| TERM-004 | RiskAssessor / 风险三态 | ALLOW / CONFIRM / DENY 的 SQL 风险评级 | `core/security/risk_assessor.py` |
| TERM-005 | result_id | 查询结果的引用 id（载荷裁剪用，≤ ~20 token） | 节省 token |
| TERM-006 | option_id | ECharts 图表的声明式 option 引用 id | `utils/chart_spec.py` |
| TERM-007 | result_store | 有界 TTL 的查询结果缓存 | `utils/result_store.py`，上限 50 条 / 10min |
| TERM-008 | checkpointer | 多轮对话短期记忆持久化 | 优先 AsyncPostgresSaver，回退 InMemory |
| TERM-009 | store | 跨会话长期记忆（remember/recall） | 静默降级 |
| TERM-010 | 载荷裁剪 | 跨轮压缩 ToolMessage，避免上下文膨胀 | middleware |
| TERM-011 | schema_max_relevant_tables | schema 召回上限 | 防上下文过载 |
| TERM-012 | sql_max_rows | 自动 LIMIT 的上限 | 防全表扫描 |
| TERM-013 | golden 集 | 回归评测的标准用例集 | `eval/golden_queries.json` |

---

*版本：v0.1（从现有文档提取） | 更新：2026-10-07*