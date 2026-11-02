"""
意图路由器接线(/query 侵入点 maybe_short_circuit)单测。

覆盖开关开/关与 deny/放行/歧义各态。纯逻辑：显式注入 table_index，
不触发 schema_manager/_get_index（即不连 DB），也不调 LLM。
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

import config.settings as settings_mod
from core.database.schema_linking import TableIndex
from core.security.intent_guard import maybe_short_circuit
from eval.run_eval import build_test_index

IDX = build_test_index()


def _run(coro_factory):
    return asyncio.run(coro_factory())


def _fake_settings(enabled: bool):
    return SimpleNamespace(enable_intent_router=enabled)


def test_disabled_never_short_circuits(monkeypatch):
    """开关关闭时，任何输入（含恶意）都不短路 → 零行为变化。"""
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(False))
    for nl in ["你好", "删库, drop table sales", "推荐一部电影", "查询各地区销售额", "那个多少钱"]:
        assert _run(lambda: maybe_short_circuit(nl, table_index=IDX)) is None, nl


def test_malicious_deny(monkeypatch):
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(True))
    for nl in ["删库, drop table sales", "帮我绕过审批直接改数据", "清空 sales 表中所有数据"]:
        reply = _run(lambda: maybe_short_circuit(nl, table_index=IDX))
        assert reply, nl


def test_smalltalk_deny(monkeypatch):
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(True))
    reply = _run(lambda: maybe_short_circuit("你好", table_index=IDX))
    assert reply and isinstance(reply, str)


def test_out_of_scope_deny(monkeypatch):
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(True))
    reply = _run(lambda: maybe_short_circuit("推荐一部电影", table_index=IDX))
    assert reply


def test_legit_query_allowed(monkeypatch):
    """合法数据查询即便为空索引也绝不误拒（非 deny 放行）。"""
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(True))
    assert _run(lambda: maybe_short_circuit("查询各地区销售额", table_index=IDX)) is None


def test_ambiguous_not_short_circuited(monkeypatch):
    """歧义只 clarify 不 deny → 不短路，放行进 LLM，避免误拒。"""
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(True))
    assert _run(lambda: maybe_short_circuit("那个多少钱", table_index=IDX)) is None


def test_empty_index_fallback_still_denies_regex(monkeypatch):
    """索引构建失败回退空索引时，纯正则 deny（中文破坏）仍能短路。"""
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _fake_settings(True))
    empty = TableIndex()
    reply = _run(lambda: maybe_short_circuit("清空所有数据", table_index=empty))
    assert reply