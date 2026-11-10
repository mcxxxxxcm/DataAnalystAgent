"""
缓存后端抽象（可插拔：memory / redis）

位置：utils/cache_backend.py
职责：为「查询结果缓存」「图表 spec 缓存」提供**接口与 BoundedTTLCache 完全同构**的可切换后端，
使 `utils/result_store.py` / `tools/chart_tools.py` 以最小改动支持多 worker 跨进程共享（backlog B006）。

对齐 state-owners 不变量：
- 单一写者：各后端实例独占其内部存储；set / 淘汰集中在后端类。
- TTL / 容量有界：memory 走 BoundedTTLCache；redis 走 SETEX(TTL 原生) + ZSET 记写入时间戳做容量淘汰。
- 非破坏读：get / peek 不删除条目（redis 用 GET；peek 连惰性回收都不触碰状态）。

降级约定（对齐 checkpointer / 长期记忆 Store）：redis 依赖未装、连不上、超时 → logging.warning 一次后
自动降级到进程内 MemoryCacheBackend，保证无 Redis 环境不崩、行为退化为原 memory。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Protocol, TypeVar

logger = logging.getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")

# 默认容量 / TTL 与 BoundedTTLCache 一致（50 条 / 600s），保持既有行为不因换后端而变。
_DEFAULT_MAX_ENTRIES = 50
_DEFAULT_TTL_SECONDS = 600.0
# 后台桥接的 Redis 命令超时（秒）；超过视为不可用 → 降级 memory。
_REDIS_CMD_TIMEOUT = 2.0


class CacheBackend(Protocol[K, V]):
    """与 BoundedTTLCache 相同的能力面；默认后端可 `get_cache_backend()` 获取。"""

    def set(self, key: K, value: V) -> None: ...
    def get(self, key: K) -> Optional[V]: ...
    def peek(self, key: K) -> Optional[V]: ...
    def pop(self, key: K) -> Optional[V]: ...
    def clear(self) -> None: ...
    def size(self) -> int: ...
    def keys(self) -> list: ...


class MemoryCacheBackend:
    """内存后端：内部仍持一个 BoundedTTLCache，单一写者与 TTL/容量语义交给缓存原语。"""

    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        from utils.bounded_cache import BoundedTTLCache
        self._cache = BoundedTTLCache(max_entries=max_entries, ttl_seconds=ttl_seconds)

    def set(self, key: K, value: V) -> None:
        self._cache.set(key, value)

    def get(self, key: K) -> Optional[V]:
        return self._cache.get(key)

    def peek(self, key: K) -> Optional[V]:
        return self._cache.peek(key)

    def pop(self, key: K) -> Optional[V]:
        return self._cache.pop(key)

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return self._cache.size()

    def keys(self) -> list:
        return self._cache.keys()


def _json_default(value: Any) -> Any:
    """JSON 序列化兜底：datetime/date → isoformat；Decimal → float。"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"无法 JSON 序列化类型 {type(value).__name__}")


class _FakeRedisClient:
    """极简内存 Redis 客户端，仅实现 cache_backend 用到的命令（供测试与无 redis 依赖时的降级路径）。"""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}
        self._z: dict[str, dict[str, float]] = {}

    async def setex(self, name: str, time_val: int, value: str) -> None:  # noqa: D102
        self._d[name] = value  # 测试不验 TTL，模拟层省略过期；语义一致由真实 redis 测试兜

    async def get(self, name: str) -> Optional[str]:  # noqa: D102
        return self._d.get(name)

    async def delete(self, name: str) -> None:  # noqa: D102
        self._d.pop(name, None)

    async def zadd(self, name: str, value: dict, **kwargs) -> None:  # noqa: D102
        z = self._z.setdefault(name, {})
        for member, score in value.items():
            z[member] = float(score)

    async def zcard(self, name: str) -> int:  # noqa: D102
        return len(self._z.get(name, {}))

    async def zremrangebyscore(self, name: str, min: Any, max: Any) -> int:  # noqa: A002,D102
        z = self._z.get(name, {})
        if min == "-inf" and (isinstance(max, (int, float)) or max == "+inf"):
            hi = float("inf") if max == "+inf" else float(max)
            keep = {m: s for m, s in z.items() if s > hi}
            removed = len(z) - len(keep)
            if keep:
                self._z[name] = keep
            else:
                self._z.pop(name, None)
            return removed
        return 0

    async def zrange(self, name: str, start: int, end: int, **kwargs) -> list:  # noqa: D102
        z = dict(sorted(self._z.get(name, {}).items(), key=lambda kv: kv[1]))
        items = list(z.keys())
        if end == -1 or end is None:
            return items[start:]
        return items[start:end + 1]

    async def zrem(self, name: str, *members) -> int:  # noqa: D102
        z = self._z.get(name, {})
        n = 0
        for m in members:
            if m in z:
                del z[m]
                n += 1
        if not z:
            self._z.pop(name, None)
        return n


class RedisCacheBackend:
    """
    Redis 后端：同步能力面对外部，内部经 `run_coroutine_threadsafe` 桥到独立后台 event loop。

    - value 走 JSON（`_json_default` 处理 datetime/Decimal）→ `SETEX key json ex=ttl`（TTL 原生）。
    - 容量有界：同名 ZSET 记录 (前缀+key → 过期时刻)，ZREMRANGEBYSCORE 惰性清过期 + 超上限淘汰最旧。
    - key 加命名空间前缀（如 `rs:` / `chart:`）防跨 owner 串写。
    - 任一无 Redis 环境 / 命令超时 / 异常 → 一次 warning 后降级到内部 MemoryCacheBackend。
    """

    def __init__(
        self,
        url: str,
        *,
        prefix: str = "ck:",
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        client: Any = None,
    ) -> None:
        self._url = url
        self._prefix = prefix
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._fallback = MemoryCacheBackend(max_entries=max_entries, ttl_seconds=ttl_seconds)
        self._client = client  # 测试注入；None 则按 url 建真实客户端

        self._down = False
        if client is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="redis-cache-loop")
            self._thread.start()
            atexit.register(self.close)
        else:
            # 测试用假客户端：无后台 loop，操作可直接同步 await
            self._loop = None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def close(self) -> None:
        """停止后台 event loop（进程退出 / 测试收尾用）。"""
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run(self, coro: Any) -> Any:
        """把协程桥到后台 loop 同步执行；异常/超时 → 标记降级并让调用回退 memory。"""
        if self._loop is None:
            # 假客户端（测试）：在临时事件循环里同步跑，避免依赖当前是否已有 loop
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=_REDIS_CMD_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 — 连接错误/超时/序列化任一失败都降级
            if not self._down:
                logger.warning("Redis 缓存后端不可用（%s），降级到进程内 memory 缓存", exc)
            self._down = True
            raise

    @property
    def _r(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._url)
        return self._client

    # ---- 序列化 ----
    def _key(self, key: K) -> str:
        return f"{self._prefix}{key}"

    @staticmethod
    def _encode(value: Any) -> str:
        return json.dumps(value, default=_json_default)

    @staticmethod
    def _decode(payload: str) -> Any:
        return json.loads(payload)

    # ---- 容量有界 / 惰性回收 ----
    def _expire_cleanup(self) -> None:
        """惰性移除已过期成员的 ZSET 记录（读路径调用，控制条目数）。"""
        now = time.time()
        if self._down:
            return
        try:
            self._run(self._r.zremrangebyscore(self._prefix, "-inf", now))
        except Exception:
            pass

    def _evict_oldest_if_needed(self) -> None:
        if self._down:
            return
        try:
            while self._run(self._r.zcard(self._prefix)) > self._max_entries:
                oldest = self._run(self._r.zrange(self._prefix, 0, 0))
                if not oldest:
                    break
                member = oldest[0]
                self._run(self._r.delete(member))
                self._run(self._r.zrem(self._prefix, member))
        except Exception:
            pass

    # ---- 能力面 ----
    def set(self, key: K, value: V) -> None:
        if self._down:
            return self._fallback.set(key, value)
        try:
            self._run(self._r.setex(self._key(key), int(self._ttl_seconds), self._encode(value)))
            self._run(self._r.zadd(self._prefix, {self._key(key): time.time() + self._ttl_seconds}))
            self._evict_oldest_if_needed()
        except Exception:
            self._fallback.set(key, value)

    def get(self, key: K) -> Optional[V]:
        if self._down:
            return self._fallback.get(key)
        try:
            self._expire_cleanup()
            payload = self._run(self._r.get(self._key(key)))
            return self._decode(payload) if payload is not None else None
        except Exception:
            return self._fallback.get(key)

    def peek(self, key: K) -> Optional[V]:
        if self._down:
            return self._fallback.peek(key)
        try:
            payload = self._run(self._r.get(self._key(key)))
            return self._decode(payload) if payload is not None else None
        except Exception:
            return self._fallback.peek(key)

    def pop(self, key: K) -> Optional[V]:
        if self._down:
            return self._fallback.pop(key)
        try:
            payload = self._run(self._r.get(self._key(key)))
            if payload is None:
                self._run(self._r.zrem(self._prefix, self._key(key)))
                return None
            self._run(self._r.delete(self._key(key)))
            self._run(self._r.zrem(self._prefix, self._key(key)))
            return self._decode(payload)
        except Exception:
            return self._fallback.pop(key)

    def clear(self) -> None:
        if self._down:
            return self._fallback.clear()
        try:
            members = self._run(self._r.zrange(self._prefix, 0, -1))
            for member in members:
                self._run(self._r.delete(member))
            self._run(self._r.zrem(self._prefix, *members))
        except Exception:
            self._fallback.clear()

    def size(self) -> int:
        if self._down:
            return self._fallback.size()
        try:
            self._expire_cleanup()
            return self._run(self._r.zcard(self._prefix))
        except Exception:
            return self._fallback.size()

    def keys(self) -> list:
        if self._down:
            return self._fallback.keys()
        try:
            self._expire_cleanup()
            return [m[len(self._prefix):] for m in self._run(self._r.zrange(self._prefix, 0, -1))]
        except Exception:
            return self._fallback.keys()


def get_cache_backend(
    *,
    backend: Optional[str] = None,
    url: Optional[str] = None,
    prefix: Optional[str] = None,
) -> CacheBackend:
    """
    按配置返回缓存后端实例。

    默认读 `settings.cache_backend`（memory / redis）。参数可覆盖（测试用）。
    memory → MemoryCacheBackend；redis 且未装依赖/连不上 → 日志告警并返回 memory 等价后端。
    """
    from config.settings import get_settings
    settings = get_settings()
    name = (backend or settings.cache_backend or "memory").lower()
    prefix = prefix or "ck:"

    if name == "redis":
        # 显式传入 url 字符串就覆盖 settings；None 表示用 settings.redis_url
        redis_url = url if url is not None else (settings.redis_url or "")
        if not redis_url:
            logger.warning("cache_backend=redis 但未配置 redis_url，回退 memory")
            return MemoryCacheBackend()
        try:
            import redis  # noqa: F401 — 探测依赖是否可 import
            return RedisCacheBackend(redis_url, prefix=prefix)
        except Exception as exc:  # noqa: BLE001 — 未装 redis 依赖
            logger.warning("cache_backend=redis 依赖不可用（%s），回退 memory", exc)
            return MemoryCacheBackend()
    return MemoryCacheBackend()