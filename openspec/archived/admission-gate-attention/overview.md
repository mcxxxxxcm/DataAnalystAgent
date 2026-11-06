# Change Overview：请求准入门 + 注意力经济（Admission Gate & Attention Economics）

> 迁移 dsh-superagent 的「does not ask unless told / acts only when a written rule allows / speaks only when a person can use a result」哲学与 Policy·admission-table 机制，落进本项目 API 入口。

## Why（为什么做）

`/query` 目前所有请求（除 `ENABLE_INTENT_ROUTER` 短路）都无差别进 LLM：无来源准入、寒暄/结构询问也烧 token，且缺乏一个「来源 × 意图 → 放行/拒/直答」的确定性入口，安全与成本都不可控、不可回归。

## What（做什么 / 不动什么）

- **新增** `core/security/admission.py`：`AdmissionGate` 确定性准入 Policy（对齐 dsh 的 gate/admission-table 思想）。
  - 来源准入：`admission_mode`（off / allowlist）下按 `admission_allowed_keys` 放行，未准入来源明确 DENY。
  - 意图×注意力经济：对 `SMALLTALK` / `INFO` 等低信号且安全意图，用**固定直答文案**（prompt text，非 LLM）直接回，不烧 token。
  - 复用 `classify_intent`，不另造检索（Avoid §4）。
- **修改** `api/routes.py`：`/query` 前置改为过 admission gate（门控 `enable_admission_gate`，默认关），替代/增强现有 `maybe_short_circuit`。
- **修改** `config/settings.py`：新增 `admission_mode` / `admission_allowed_keys` / `intent_canonical_replies` 配置与默认值。
- **测试** 新增 `tests/test_admission.py`。
- **不做**：不引入多用户/账号体系、不改 HITL 审批语义、不接数据库存 admission 表（保留纯配置 + 代码内默认）。

## How（怎么落地，一句概览）

写一个纯逻辑 `AdmissionGate.compute(text, source)` 返回 `AdmissionVerdict`（admit/deny/clarify/reply），`/query` 在 `enable_admission_gate=True` 时优先走它；其余路径行为不变。

---

- 关联模块：`core/security/` · `api/routes.py` · `config/settings.py`
- 关联 CAP：CAP-SEC-009（意图路由）· TASK-BACKLOG-010（准入/滥用）· CAP-API-005
- 涉及测试：`tests/test_admission.py`（新增）；`tests/test_intent_router_wiring.py`（保持通过）