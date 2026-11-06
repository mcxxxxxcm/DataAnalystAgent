# Change Proposal：请求准入门 + 注意力经济

> 设计文档，给人 review 用。迁移 dsh-superagent 的 Policy / admission-table / gate 思想。

## 方案

### 现状
- `/query`（`api/routes.py:332`）仅当 `enable_intent_router=True` 时经 `maybe_short_circuit` 对明确 deny 意图短路；其余全部进 LLM。
- 无「来源准入」：任何能打透 API 的请求（相同 Bearer 或开放时所有来源）一律可达 LLM。
- 寒暄/结构询问都烧 LLM token（每次全量计费），与 dsh「speaks only when a person can use a result」相悖。
- `IntentVerdict` 已含 `deny/clarify/reply` 语义，可复用。

### 目标
- 新增确定性**准入 Policy**：来源 × 意图合成一个 `AdmissionVerdict`，在入口处决定 admit / deny / clarify / direct-reply。
- **注意力经济**：低信号安全意图（SMALLTALK/部分 INFO）由固定文案直答，零 LLM 调用。
- 全部门控默认关，接通不影响现状（向后兼容）。

### 改动清单
- **新建** `core/security/admission.py`
  - `class AdmissionMode(str,Enum)`: `OFF` / `ALLOWLIST`。
  - `@dataclass AdmissionVerdict`: `admit:bool`、`action: Literal['admit','deny','clarify','reply']`、`reason`、`reply: Optional[str]`。
  - `class AdmissionGate`: 构造时读 settings；`compute(text, source) -> AdmissionVerdict`（纯逻辑，无 DB/LLM）。
  - 来源准入：`mode=ALLOWLIST` 时 `source`（请求头 `X-Admission-Key` / 内置 default）必须在 `admission_allowed_keys`；否则 DENY「来源未准入」。
  - 意图判定：复用 `classify_intent`；deny 意图（MALICIOUS/OUT_OF_SCOPE）→ deny；`SMALLTALK` 且 `mode` 允许直答 → reply（文案取自 `intent_canonical_replies`，兜底已有文案）；`INFO` 且命中白名单 key 可直答固定说明；否则 admit（放行进 Agent）。
  - 提供 `async maybe_gate(text, source=None)` 供 `/query` 用（与 `maybe_short_circuit` 同形，返回 `Optional[str]`，admit 返回 None）。
- **修改** `config/settings.py`：新增
  - `enable_admission_gate: bool=False`
  - `admission_mode: str='off'`（`off|allowlist`）
  - `admission_allowed_keys: Optional[str]=None`（逗号分隔，allowlist 模式来源 key）
  - `intent_canonical_replies: Optional[str]=None`（`意图=文案` 段，parse 成 dict）
- **修改** `api/routes.py` `/query`：`enable_admission_gate=True` 时先 `await maybe_gate(...)`，命中 deny/reply 直接返回，不再走 LLM；否则沿用旧逻辑。
- **测试** `tests/test_admission.py`：来源准入、意图拒答、SMALLTALK/INFO 直答、门控关闭时放行、纯函数无 LLM/DB。

## 取舍 / 风险

| 决策点 | 选了什么 | 理由 | 代价 |
|--------|----------|------|------|
| 准入来源以「key allowlist」而非完整账号体系 | key allowlist | 轻量、可配置、与现有 Bearer token 互补而非推翻 | 无多用户粒度 |
| 门控默认关 | 默认 `enable_admission_gate=False` | 保守低风险，接通不破坏现状；与 intent_router 同理 | 需显式开启才有收益 |
| 直答文案放配置（prompt text）而非硬编码 | 配置+兜底 | dsh「behavior in words is prompt text」；可运维调整 | 多一项配置 |

## 兼容性
- 新增配置均有默认值，`enable_admission_gate=False` 时 `/query` 行为与现在完全一致。
- `maybe_short_circuit`/`intent_guard` 保留不动，admission gate 在其**之前**或**并行**接入（Gate 内部可复用之判定结果），不删旧入口。
- 前端字段不变。

## 测试计划
- `tests/test_admission.py`：`Gate` 来源准入、意图 deny、SMALLTALK/INFO 直答文案、OFF 模式全放行、`maybe_gate` 门控开关行为。