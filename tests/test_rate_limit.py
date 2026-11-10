"""滑动窗口限流（B010）测试：限下放行/超限拒绝/窗口滑动/per-key 隔离/no-op。"""

import time

from core.security.rate_limit import SlidingWindowLimiter, parse_rate_limit


def test_under_limit_allowed():
    lim = SlidingWindowLimiter(limit=3, window_seconds=10)
    assert lim.allow("k") is True
    assert lim.allow("k") is True
    assert lim.allow("k") is True


def test_over_limit_rejected():
    lim = SlidingWindowLimiter(limit=2, window_seconds=10)
    assert lim.allow("k") is True
    assert lim.allow("k") is True
    assert lim.allow("k") is False


def test_window_slides():
    lim = SlidingWindowLimiter(limit=1, window_seconds=0.05)
    assert lim.allow("k") is True
    assert lim.allow("k") is False
    time.sleep(0.1)
    assert lim.allow("k") is True  # 窗口已滑动


def test_per_key_isolation():
    lim = SlidingWindowLimiter(limit=1, window_seconds=10)
    assert lim.allow("a") is True
    assert lim.allow("a") is False
    assert lim.allow("b") is True  # 互不影响


def test_empty_key_not_recorded():
    lim = SlidingWindowLimiter(limit=1, window_seconds=10)
    assert lim.allow("") is True
    assert lim.allow(None) is True


def test_parse_rate_limit_variants():
    assert parse_rate_limit("10/min")._window_seconds == 60
    assert parse_rate_limit("5/h")._limit == 5
    assert parse_rate_limit("1000/d")._window_seconds == 86400
    assert parse_rate_limit("") is None
    assert parse_rate_limit("abc") is None
    assert parse_rate_limit("0/m") is None


def test_parse_off_is_noop():
    # None/空 = 不启用 → 调用方不实例化，等同 no-op
    assert parse_rate_limit(None) is None