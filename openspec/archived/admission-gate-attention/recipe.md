# Change Recipe：请求准入门 + 注意力经济（执行剧本）

> 给 LLM 的逐步执行清单。每步 = Context + Action + Validation。执行后逐条自检打 `[x]`。

## Step 1 —— 读约定
- **Context**: 动手前对齐项目宪法，避免违反分层/安全红线/Avoid。
- **Action**: 读 `openspec/agreement.md`，确认本 change 属 `core/security` + `api` + `config` 层；新增工具不触 SQL 执行、不放松权限。
- **Validation**: 已确认分层归属与「不新增高危能力」。 `[ ]`

## Step 2 —— 新增配置项
- **Context**: admissions/直答文案需要配置承载并给默认值（不硬编码）。
- **Action**: 在 `config/settings.py` 新增 `enable_admission_gate=False`、`admission_mode='off'`、`admission_allowed_keys: Optional[str]=None`、`intent_canonical_replies: Optional[str]=None`；给 `user_admission_key_map` / `canonical_reply_map` 解析属性（逗号、`=`分隔，容错段格式，对齐 `user_synonym_map` 写法）。
- **Validation**: `py -m pytest tests/test_settings_defaults.py -q` 通过；新增属性返回正确 dict。 `[ ]`

## Step 3 —— 写 AdmissionGate（纯逻辑）
- **Context**: 复现 dsh `gate(trigger)` 的思想：来源×意图合成确定性准入判定，不触 DB/LLM。
- **Action**: 新建 `core/security/admission.py`：`AdmissionMode`、`AdmissionVerdict`(admit/action/reason/reply)、`AdmissionGate.compute(text, source)->AdmissionVerdict`、`async maybe_gate(text, source)->Optional[str]`。意图复用 `classify_intent`；allowlist 模式校验来源 key；SMALLTALK/INFO 命中白名单 key → 直答（文案取 `intent_canonical_replies`，兜底内置）。门控读取 `admission_mode`/`enable_admission_gate`。
- **Validation**: 独立跑：`admit`/`deny`/`reply` 分支逻辑可被单测覆盖；不 import DB。 `[ ]`

## Step 4 —— 接线 `/query`
- **Context**: 让准入在入口生效，但门控默认关，接通不破坏现状。
- **Action**: 修改 `api/routes.py` `/query`：`enable_admission_gate=True` 时先 `await maybe_gate(request.query, source=request.headers.get('X-Admission-Key'))`；返回非 None 直接 `QueryResponse(success=False, message=..., thread_id=...)`；否则沿用旧流程。source 从请求头取，容错 None。
- **Validation**: 新增 `tests/test_admission.py` 覆盖：门控开+拒绝→短路；门控开+放行→走 agent（mock）；门控关→旧行为。 `[ ]`

## Step 5 —— 测试
- **Context**: 测试是硬门槛，且不能破坏现有 intent_router 相关测试。
- **Action**: 新增 `tests/test_admission.py`；更新 `tests/test_settings_defaults.py`（如新增默认断言）；`py -m pytest tests/ -q`。
- **Validation**: 全绿（基线 138 + 新增用例）。 `[ ]`

## Final —— 收尾自检
- 对照 overview How 逐条兑现。更新 `README.md`（如暴露准入配置）。本 change 目录移至 `openspec/archived/`。提交信息中文主题。 `[ ]`