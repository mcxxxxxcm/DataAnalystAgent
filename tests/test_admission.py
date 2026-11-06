"""
请求准入门 + 注意力经济 测试。

验证 AdmissionGate 的「来源 × 意图 → 准入判定」、注意力经济直答、maybe_gate 门控行为。
纯逻辑，不触 DB/LLM。async 入口用 asyncio.run（与 test_intent_router_wiring 同款，无需 pytest-asyncio）。
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from core.security.admission import AdmissionGate, maybe_gate
from eval.run_eval import build_test_index

IDX = build_test_index()


def _run(coro_factory):
    return asyncio.run(coro_factory())


def _settings(**over):
    base = dict(
        enable_admission_gate=True,
        admission_mode="off",
        allowed_admission_keys=set(),
        canonical_reply_map={},
        enable_intent_router=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestCompute:
    def test_admit_query_in_off_mode(self):
        gate = AdmissionGate(settings=_settings(admission_mode="off"), table_index=IDX)
        v = gate.compute("各地区销售总额多少", source=None)
        assert v.admit and v.action == "admit"

    def test_malicious_denied(self):
        gate = AdmissionGate(settings=_settings(admission_mode="off"), table_index=IDX)
        v = gate.compute("drop table sales;", source=None)
        assert not v.admit and v.action == "deny"

    def test_allowlist_rejects_missing_key(self):
        s = _settings(admission_mode="allowlist", allowed_admission_keys={"team-a"})
        gate = AdmissionGate(settings=s, table_index=IDX)
        v = gate.compute("销售总额多少", source=None)
        assert not v.admit and v.action == "deny"

    def test_allowlist_admits_valid_key(self):
        s = _settings(admission_mode="allowlist", allowed_admission_keys={"team-a"})
        gate = AdmissionGate(settings=s, table_index=IDX)
        v = gate.compute("销售总额多少", source="TEAM-A")
        assert v.admit and v.action == "admit"

    def test_allowlist_mode_without_keys_denies(self):
        s = _settings(admission_mode="allowlist", allowed_admission_keys=set())
        gate = AdmissionGate(settings=s, table_index=IDX)
        v = gate.compute("销售总额多少", source="x")
        assert not v.admit and v.action == "deny"


class TestAttentionEconomics:
    def test_smalltalk_gets_default_reply(self):
        gate = AdmissionGate(settings=_settings(admission_mode="off"), table_index=IDX)
        v = gate.compute("你好", source=None)
        assert v.action == "reply"
        assert v.reply and "数据分析" in v.reply

    def test_smalltalk_uses_canonical_reply_when_configured(self):
        s = _settings(admission_mode="off", canonical_reply_map={"smalltalk": "你好！请讲。"})
        gate = AdmissionGate(settings=s, table_index=IDX)
        v = gate.compute("你好", source=None)
        assert v.action == "reply"
        assert v.reply == "你好！请讲。"

    def test_info_replies_when_configured(self):
        s = _settings(admission_mode="off", canonical_reply_map={"info": "可用：sales, orders"})
        gate = AdmissionGate(settings=s, table_index=IDX)
        v = gate.compute("sales 表有哪些字段", source=None)
        assert v.action == "reply"
        assert v.reply == "可用：sales, orders"

    def test_info_admits_when_not_configured(self):
        gate = AdmissionGate(settings=_settings(admission_mode="off"), table_index=IDX)
        v = gate.compute("sales 表有哪些字段", source=None)
        assert v.admit and v.action == "admit"


class TestMaybeGate:
    def test_disabled_returns_none(self):
        s = _settings(enable_admission_gate=False, admission_mode="off")
        assert _run(lambda: maybe_gate("你好", source=None, settings=s, table_index=IDX)) is None

    def test_deny_shortcircuits(self):
        s = _settings(enable_admission_gate=True, admission_mode="off")
        out = _run(lambda: maybe_gate("drop table sales;", source=None, settings=s, table_index=IDX))
        assert out is not None

    def test_clarify_passes_through(self):
        # 歧义→clarify 不进 LLM 但也不短路（保守低误杀）：返回 None
        s = _settings(enable_admission_gate=True, admission_mode="off")
        out = _run(lambda: maybe_gate("数据分析一下", source=None, settings=s, table_index=IDX))
        assert out is None

    def test_reply_shortcircuits_with_canonical(self):
        s = _settings(enable_admission_gate=True, admission_mode="off",
                      canonical_reply_map={"smalltalk": "你好！"})
        out = _run(lambda: maybe_gate("你好", source=None, settings=s, table_index=IDX))
        assert out == "你好！"

    def test_allowlist_source_honored(self):
        s = _settings(enable_admission_gate=True, admission_mode="allowlist",
                      allowed_admission_keys={"a"})
        denied = _run(lambda: maybe_gate("销售总额多少", source=None, settings=s, table_index=IDX))
        assert denied is not None
        admitted = _run(lambda: maybe_gate("销售总额多少", source="a", settings=s, table_index=IDX))
        assert admitted is None