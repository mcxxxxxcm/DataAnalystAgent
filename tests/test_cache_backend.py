"""缓存后端抽象（B006）测试：memory/redis 同构、TTL、容量、序列化、降级。"""

from datetime import datetime
from decimal import Decimal

import pytest

from utils.cache_backend import (
    MemoryCacheBackend,
    RedisCacheBackend,
    get_cache_backend,
    _FakeRedisClient,
)


def _fake_redis(get_settings_kwargs=None):
    """构造一个走假 Redis 客户端的后端实例（不启真实后台 loop，可测方法逻辑）。"""
    return RedisCacheBackend("redis://fake", prefix="t:", client=_FakeRedisClient())


def test_memory_roundtrip():
    b = MemoryCacheBackend()
    b.set("k", {"n": 1})
    assert b.get("k") == {"n": 1}
    assert b.peek("k") == {"n": 1}  # 非摧毁读
    assert b.size() == 1


def test_memory_ttl_expiry():
    b = MemoryCacheBackend(ttl_seconds=0.05)
    b.set("k", 2)
    assert b.get("k") == 2
    import time
    time.sleep(0.1)
    assert b.get("k") is None
    assert b.size() == 0


def test_memory_evict_oldest_on_capacity():
    b = MemoryCacheBackend(max_entries=2)
    b.set("a", 1)
    b.set("b", 2)
    b.set("c", 3)
    assert b.size() == 2
    # 淘汰最早写入的 a；b、c 仍在
    assert sorted(b.keys()) in (["b", "c"], ["c", "b"])
    assert {b.get("b"), b.get("c")} == {2, 3}


def test_redis_roundtrip_and_namespace():
    r = _fake_redis()
    r.set("x", {"v": [1, 2]})
    assert r.get("x") == {"v": [1, 2]}
    assert r.peek("x") == {"v": [1, 2]}
    # 命名空间前缀不串
    r2 = RedisCacheBackend("redis://fake", prefix="other:", client=_FakeRedisClient())
    r2.set("x", {"v": 9})
    assert r.get("x") == {"v": [1, 2]}  # t: 前缀
    assert r2.get("x") == {"v": 9}      # other: 前缀


def test_redis_pop_and_endpoint():
    r = _fake_redis()
    r.set("p", "val")
    assert r.pop("p") == "val"
    assert r.get("p") is None
    assert r.pop("p") is None
    assert r.size() == 0


def test_redis_datetime_decimal_serialization():
    r = _fake_redis()
    r.set("d", {"ts": datetime(2026, 11, 9, 12, 0), "amt": Decimal("3.14")})
    got = r.get("d")
    assert got["ts"] == "2026-11-09T12:00:00"
    assert got["amt"] == 3.14


def test_redis_clear_and_keys():
    r = _fake_redis()
    r.set("a", 1)
    r.set("b", 2)
    assert set(r.keys()) == {"a", "b"}
    r.clear()
    assert r.size() == 0
    assert r.keys() == []


def test_redis_evict_oldest_on_capacity():
    r = RedisCacheBackend("redis://fake", prefix="t:", max_entries=2, client=_FakeRedisClient())
    r.set("a", 1)
    r.set("b", 2)
    r.set("c", 3)
    assert r.size() == 2
    assert sorted(r.keys()) in (["b", "c"], ["c", "b"])


def test_get_cache_backend_default_memory():
    # settings 默认 memory
    b = get_cache_backend()
    assert isinstance(b, MemoryCacheBackend)


def test_get_cache_backend_redis_no_url_falls_back():
    # cache_backend=redis 但 redis_url 为空 → 直接回退 memory（不依赖真实 redis）
    b = get_cache_backend(backend="redis", url="")
    assert isinstance(b, MemoryCacheBackend)


def test_get_cache_backend_no_redis_module_falls_back(monkeypatch):
    # 未装 redis 依赖 → 回退 memory
    import sys
    class Blocker:
        def __getattr__(self, name):
            raise ImportError("No module named 'redis'")
    monkeypatch.setitem(sys.modules, "redis", Blocker())
    monkeypatch.delitem(sys.modules, "redis.asyncio", raising=False)
    b = get_cache_backend(backend="redis", url="redis://127.0.0.1:6399")
    assert isinstance(b, MemoryCacheBackend)