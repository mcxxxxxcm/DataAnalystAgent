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
| TERM-013 | 评测语料集 | 回归评测的分类标准用例集 | `eval/cases/`（schema_linking / security_deny / routing_guard 三文件）；golden 旧路径已弃 |
| TERM-014 | 意图路由器 intent_guard | 确定性 NL 意图分类（query/chart/info/malicious/smalltalk/ambiguous/out_of_scope），带 deny/clarify 语义；`maybe_short_circuit` 已接线 `/query`，仅短路 deny | `core/security/intent_guard.py`；`ENABLE_INTENT_ROUTER` 默认关 |
| TERM-015 | 写操作边界 | query_database 分派 INSERT/UPDATE/DELETE → 返回受影响行数；`enable_sql_write` 默认关 + HITL 强制人审；DELETE/UPDATE 无 WHERE 仍 DENY | `tools/sql_tools.py` / `core/security/risk_assessor.py` |
| TERM-016 | 模型视图可重建（recon） | "Model-visible ⟺ logged"：发给模型的完整消息序列可由会话日志确定性重建；工具日志记录真实 thread_id + `model_view`（与送入 LLM 同 condense 阈值） | `core/recon.py` / `middleware/logging_wrapper.py`；`recon_model_view_enabled` 默认开 |
| TERM-017 | 请求准入门（admission gate） | 「来源 × 意图」合成确定性准入判定（admit/deny/clarify/reply）；迁移 dsh 的 Policy/gate/admission-table + 注意力经济 | `core/security/admission.py`；`enable_admission_gate` 默认关、`admission_mode=allowlist` 校验来源 key |
| TERM-018 | 注意力经济 | 只在「有人必须行动或能用到结果」时才应答/计算；低信号安全意图（寒暄/结构询问）固定直答不烧 LLM | `core/security/admission.py` `maybe_gate`；文案经 `intent_canonical_replies`（prompt text，非硬编码） |
| TERM-019 | 单一写者（one-writer-per-state） | 每类可变状态只允许一个写者，其余只读或委托；读查询不写 | `utils/bounded_cache.py` / `docs/state-owners.md` |
| TERM-020 | 效果队列（effect queue） | 可重试副作用按 key 幂等入队、指数退避重试、可选持久化、失败健康计数 | `utils/effect_queue.py`；`effect_queue_max_retries>0` 时接通 SQL 瞬时错误退避层 |

---

*版本：v0.2（补准入门/注意力经济/单一写者/效果队列） | 更新：2026-11-06*