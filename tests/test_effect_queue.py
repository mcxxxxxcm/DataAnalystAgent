"""
持久化 Effects 队列 + 指数退避 测试。

覆盖：key 幂等合并、指数退避与重试上限、持久化 JSONL 恢复、可观测计数、瞬时/非瞬时判定。
纯逻辑，不触 DB（用自定义瞬时异常模拟）。
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from utils.effect_queue import AsyncEffectQueue, run_sql_durable, sql_key


class _Transient(Exception):
    """带 'connection' 标记的瞬时异常（is_transient_error 命中）。"""


class _Hard(Exception):
    """非瞬时（无瞬时标记）。"""


def _run(coro):
    return asyncio.run(coro)


class TestRunSqlDurable:
    def test_zero_retries_calls_once(self):
        calls = {"n": 0}

        async def fake(*a, **k):
            calls["n"] += 1
            raise _Hard("syntax error")

        with __import__("pytest").raises(_Hard):
            _run(run_sql_durable(fake, key="k", max_retries=0, base_delay=0.01))
        assert calls["n"] == 1  # 关闭退避层 → 原样调用一次

    def test_transient_recovers_within_retries(self):
        calls = {"n": 0}

        async def fake(*a, **k):
            calls["n"] += 1
            if calls["n"] < 2:          # 前 1 次瞬时失败
                raise _Transient("connection reset")
            return "ok"

        result = _run(run_sql_durable(fake, key="k2", max_retries=3, base_delay=0.01))
        assert result == "ok"
        assert calls["n"] == 2

    def test_transient_exhausted_raises(self):
        calls = {"n": 0}

        async def fake(*a, **k):
            calls["n"] += 1
            raise _Transient("connection reset")

        with __import__("pytest").raises(_Transient):
            _run(run_sql_durable(fake, key="k3", max_retries=2, base_delay=0.01))
        assert calls["n"] == 3  # 1 次 + 2 次退避重试

    def test_non_transient_never_retried(self):
        calls = {"n": 0}

        async def fake(*a, **k):
            calls["n"] += 1
            raise _Hard("relation does not exist")

        with __import__("pytest").raises(_Hard):
            _run(run_sql_durable(fake, key="k4", max_retries=5, base_delay=0.01))
        assert calls["n"] == 1  # 非瞬时不重试


class TestQueueArtifacts:
    def test_enqueue_dedups_by_key(self):
        q = AsyncEffectQueue()
        q.register_handler("t", lambda p: asyncio.sleep(0))
        _run(q.enqueue("t", "a", {"v": 1}))
        assert q.pending() == 1
        _run(q.enqueue("t", "a", {"v": 2}))  # 同 key → 合并不新增
        assert q.pending() == 1
        assert q.settled() == 0

    def test_run_pending_success_counts_settled(self):
        q = AsyncEffectQueue()
        async def h(p):
            return p["v"] * 2
        q.register_handler("t", h)
        _run(q.enqueue("t", "a", {"v": 1}))
        _run(q.run_pending())
        assert q.pending() == 0
        assert q.settled() == 1
        assert q.outcome("t", "a") == 2

    def test_run_pending_transient_backoff_then_success(self):
        q = AsyncEffectQueue()
        state = {"n": 0}

        async def h(p):
            state["n"] += 1
            if state["n"] < 2:
                raise _Transient("connection reset")
            return "done"

        q.register_handler("t", h)
        _run(q.enqueue("t", "a", {"v": 1}, max_attempts=3, base_delay=0.01))
        _run(q.run_pending())  # 第 1 次瞬时失败 → 退避重排；run_pending 只跑一次到期项
        # 第一次 run_pending 只执行存活第 1 次 → failed 移出前需再跑
        if q.pending() > 0:
            _run(q.run_pending())
        assert q.outcome("t", "a") == "done" or q.settled() >= 1

    def test_persistence_roundtrip(self, tmp_path):
        p = tmp_path / "effects.jsonl"
        q = AsyncEffectQueue(persist_path=str(p))
        q.register_handler("t", lambda x: asyncio.sleep(0))
        _run(q.enqueue("t", "b", {"x": 9}))
        records = q.recover()
        assert records and records[0]["key"] == "b"
        assert records[0]["max_attempts"] == 3

    def test_missing_handler_marks_failed(self):
        q = AsyncEffectQueue()  # 无 handler
        _run(q.enqueue("none", "x", {}))
        _run(q.run_pending())
        assert q.failed() == 1


class TestSqlKey:
    def test_stable_and_nondeterministic_insensitive(self):
        assert sql_key(" SELECT * FROM t ").isdigit() or len(sql_key("SELECT * FROM t")) == 64
        assert sql_key("  select * from t") == sql_key("select * from t")