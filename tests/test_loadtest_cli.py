"""
bench.loadtest CLI 参数解析单测
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


def test_default_concurrency_for_endpoints():
    from bench.loadtest import EP_STYLES, _resolve

    assert _resolve(EP_STYLES["health"]["default_concurrency"], None) == 20
    assert _resolve(EP_STYLES["query"]["default_concurrency"], None) == 5
    # 显式给定优先
    assert _resolve(5, 10) == 10


def test_parser_query_requires_query():
    from bench.loadtest import build_parser

    p = build_parser()
    args = p.parse_args(["--endpoint", "query", "--query", "本月销售额", "--requests", "5"])
    assert args.endpoint == "query"
    assert args.query == "本月销售额"


def test_parser_thread_mode_default():
    from bench.loadtest import build_parser

    args = build_parser().parse_args(["--requests", "10"])
    assert args.thread_mode == "unique"


def test_dry_run_flag():
    from bench.loadtest import build_parser

    args = build_parser().parse_args(["--dry-run"])
    assert args.dry_run is True


def test_thread_id_strategies():
    from bench.loadtest import _thread_id_for
    import argparse

    def _args(mode):
        a = argparse.Namespace()
        a.thread_mode = mode
        return a

    u = _thread_id_for(_args("unique"), 0, 1)
    assert u != _thread_id_for(_args("unique"), 0, 2)  # unique 每次不同
    r1 = _thread_id_for(_args("reuse"), 0, 1)
    r2 = _thread_id_for(_args("reuse"), 5, 99)
    assert r1 == r2  # reuse 共用同一 thread
    p1 = _thread_id_for(_args("per-worker"), 3, 1)
    p2 = _thread_id_for(_args("per-worker"), 3, 2)
    p3 = _thread_id_for(_args("per-worker"), 4, 1)
    assert p1 == p2 and p1 != p3  # per-worker 按 worker 固定