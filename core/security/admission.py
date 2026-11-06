"""
确定性请求准入门 + 注意力经济

位置：core/security/admission.py
职责：在 /query 入口合成「来源 × 意图」的确定性准入判定（AdmissionVerdict），
实现对 dsh-superagent「acts only when a written rule allows / speaks only when a person can use a result」的迁移：
- 来源准入：allowlist 模式下，未在 admission_allowed_keys 的来源明确 DENY；
- 注意力经济：对低信号且安全的意图（SMALLTALK / INFO）用固定文案直接应答，不烧 LLM token；
- deny 意图（MALICIOUS / OUT_OF_SCOPE）照常拒绝。

纯逻辑、无 DB / 无 LLM；settings 在构造时注入（默认懒取全局 get_settings），
table_index 由调用方解析后传入（compute 为同步纯函数，不触库）。
意图判定复用 core/security/intent_guard.classify_intent（Avoid §4：不另造检索）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.security.intent_guard import Intent, classify_intent  # type: ignore


class AdmissionMode(str, Enum):
    """来源准入模式"""
    OFF = "off"              # 不校验来源，仅意图判定
    ALLOWLIST = "allowlist"  # 校验来源 key 是否在 admission_allowed_keys


@dataclass
class AdmissionVerdict:
    """合成准入判定。admit=True 且 action=='admit' 时放行进 Agent。"""
    admit: bool
    action: str                # admit / deny / clarify / reply
    reason: str
    reply: Optional[str] = None
    category: Optional[str] = None


class AdmissionGate:
    """请求准入门：来源×意图 → AdmissionVerdict。settings/table_index 构造注入，便于单测。"""

    _DEFAULT_SMALLTALK_REPLY = "你好，我是数据分析助手，请问你想查哪些数据？"

    def __init__(self, settings=None, table_index=None, allow_smalltalk: bool = True) -> None:
        self._settings = settings
        self._table_index = table_index
        self._allow_smalltalk = allow_smalltalk

    def _cfg(self):
        if self._settings is not None:
            return self._settings
        from config.settings import get_settings
        return get_settings()

    def _index(self):
        return self._table_index

    def compute_source_admission(self, source: Optional[str]) -> Optional[str]:
        """来源准入：ALLOWLIST 下校验 key；不通过返回拒绝原因，通过返回 None。"""
        cfg = self._cfg()
        if cfg.admission_mode != AdmissionMode.ALLOWLIST.value:
            return None
        allowed = cfg.allowed_admission_keys
        if not allowed:
            return "准入门处于 allowlist 模式但未配置 admission_allowed_keys"
        key = (source or "").strip().lower()
        if not key or key not in allowed:
            return "来源未准入（缺少合法的 X-Admission-Key）"
        return None

    def compute(self, text: str, source: Optional[str] = None) -> AdmissionVerdict:
        """合成准入判定（纯逻辑，无 DB / 无 LLM）。"""
        text = (text or "").strip()
        if not text:
            return AdmissionVerdict(False, "clarify", "输入为空，需要澄清具体查询", category=Intent.AMBIGUOUS.value)

        # 1) 来源准入（allowlist 模式）
        denier = self.compute_source_admission(source)
        if denier is not None:
            return AdmissionVerdict(False, "deny", denier)

        # 2) 意图判定
        verdict = classify_intent(text, self._index(), allow_smalltalk=self._allow_smalltalk)
        cat = verdict.category
        if cat == Intent.AMBIGUOUS:
            return AdmissionVerdict(False, "clarify", verdict.reason, category=cat.value)
        if cat in (Intent.MALICIOUS, Intent.OUT_OF_SCOPE):
            return AdmissionVerdict(False, "deny", verdict.reason, reply=verdict.reply, category=cat.value)

        # 3) 注意力经济：低信号且安全意图固定直答（不烧 LLM）
        replies = self._cfg().canonical_reply_map
        if cat == Intent.SMALLTALK:
            return AdmissionVerdict(
                False, "reply",
                "寒暄/低信号请求，按注意力经济直答",
                reply=replies.get("smalltalk") or verdict.reply or self._DEFAULT_SMALLTALK_REPLY,
                category=cat.value,
            )
        if cat == Intent.INFO:
            if "info" in replies:
                return AdmissionVerdict(
                    False, "reply", "结构询问按注意力经济直答", reply=replies["info"], category=cat.value
                )

        # 4) 其余（QUERY / CHART / 未配置直答的 INFO）放行
        return AdmissionVerdict(True, "admit", "来源与意图均通过准入门", category=cat.value)


async def maybe_gate(
    text: str,
    source: Optional[str] = None,
    settings=None,
    table_index=None,
) -> Optional[str]:
    """
    供 /query 使用的入口（与 maybe_short_circuit 同形）：返回非 None 应短路。
    仅当 settings.enable_admission_gate=True 才判定；admit 返回 None（放行）。
    table_index 缺省惰性取全局 schema_manager 索引，失败回退空索引。
    """
    cfg = settings or _lazy_settings()
    if not cfg.enable_admission_gate:
        return None
    idx = table_index
    if idx is None:
        idx = await _resolve_table_index()
    gate = AdmissionGate(settings=cfg, table_index=idx)
    verdict = gate.compute(text, source)
    # 仅 deny / reply（来源未准入门、恶意/离题、寒暄/结构直答）才短路；
    # clarify（歧义）放行进 LLM，对齐「保守低误杀」：宁可让歧义走 LLM，也不误拒合法查询。
    if verdict.action in ("deny", "reply"):
        return verdict.reply or verdict.reason
    return None


def _lazy_settings():
    from config.settings import get_settings
    return get_settings()


async def _resolve_table_index():
    """惰性构建检索索引；失败回退空索引（纯正则 deny 不依赖实体命中）。"""
    try:
        from core.database import schema_manager
        return await schema_manager._get_index()
    except Exception:
        from core.database.schema_linking import TableIndex
        return TableIndex()