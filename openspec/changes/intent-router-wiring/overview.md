# Change Overview：意图路由器接线 `/query`（前置拒答/澄清，节省 LLM 成本）

## Why（为什么做）

`core/security/intent_guard.py` 的确定性意图分类器已实现且可单测，但 `ENABLE_INTENT_ROUTER` 默认关、仅评测直调；运行时 `/query` 仍把所有请求（含恶意 / 寒暄 / 离题）全量送进 LLM，浪费 token、扩大风险面。优秀 guardrails 项目（NeMo Guardrails / RouteLLM / rebuff）共通做法是「廉价确定性前置门在进 LLM 前短路明确非查询请求」。

## What（做什么 / 不动什么）

- 在 `core/security/intent_guard.py` 加一个 `maybe_short_circuit(query)` **纯函数**适配器：仅在 `verdict.deny`（MALICIOUS / SMALLTALK / OUT_OF_SCOPE）时返回简短文案，否则返回 `None`。
- 在 `api/routes.py` 的 `/query` 入口、调用 Agent 之前插入该门：返回非空即直接返回 `QueryResponse(success=False, message=...)`，**不调用 LLM**。
- **不动**：`classify_intent` 本体、`table_index` 语义、任何安全校验/HITL；**不做** `clarify`（歧义）短路——一律放行进 LLM，避免误拒合法查询（对齐 intent_guard「保守、低误杀」设计约束）。
- 影响层：`core/security/`（+1 适配器）+ `api/`（接线）。默认仍 `ENABLE_INTENT_ROUTER=False` → 零行为变化。

## How（怎么落地，一句概览）

加一个只读 `settings.enable_intent_router && verdict.deny` 就短路返回文案的纯函数，塞进 `/query` 入口，配一组不连 DB/LLM 的单测。

---

- 关联模块：TASK-BACKLOG-004 · `core/security/intent_guard.py` · `api/routes.py` · `config/settings.py`（读不改）
- 涉及测试：`tests/test_intent_guard.py`（新增短路用例）或 `tests/test_intent_router_wiring.py`