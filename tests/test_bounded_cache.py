"""
BoundedTTLCache 原语测试：容量/淘汰/TTL/只读与摧毁式读语义。
"""
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.bounded_cache import BoundedTTLCache


def test_get_returns_none_for_missing_key():
    c = BoundedTTLCache()
    assert c.get("nope") is None
    assert c.size() == 0


def test_set_and_get_roundtrip():
    c = BoundedTTLCache()
    c.set("a", {"v": 1})
    assert c.get("a") == {"v": 1}
    assert c.size() == 1


def test_peek_does_not_mutate():
    c = BoundedTTLCache()
    c.set("a", 1)
    assert c.peek("a") == 1
    assert c.peek("a") == 1  # 读多次仍在
    assert c.size() == 1


def test_get_is_non_destructive():
    # 读路径不改变条目集（未过期的键读多次仍在）——对齐「Read queries never write」
    c = BoundedTTLCache()
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.size() == 1
    assert c.get("a") == 1


def test_pop_is_destructive():
    c = BoundedTTLCache()
    c.set("a", 1)
    assert c.pop("a") == 1
    assert c.get("a") is None
    assert c.size() == 0


def test_evicts_oldest_when_over_capacity():
    # 淘汰策略：超上限时淘汰最早过期的条目（单一写者的淘汰职责）
    c = BoundedTTLCache(max_entries=2)
    c.set("a", 1)
    time.sleep(0.01)
    c.set("b", 2)
    time.sleep(0.01)
    c.set("c", 3)  # 超过 2 → 淘汰 a
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3
    assert c.size() == 2


def test_expiry_invalidates_entry():
    c = BoundedTTLCache(ttl_seconds=0.05)
    c.set("a", 1)
    assert c.get("a") == 1
    time.sleep(0.08)
    assert c.get("a") is None  # 过期自动失效
    assert c.size() == 0


def test_clear_resets():
    c = BoundedTTLCache()
    c.set("a", 1)
    c.clear()
    assert c.size() == 0
    assert c.get("a") is None