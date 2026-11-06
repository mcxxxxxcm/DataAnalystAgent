"""
有界 TTL 缓存原语（单一写者）

位置：utils/bounded_cache.py
职责：提供一个「单一写者」的进程内有界 TTL 缓存。所有写路径（set / 过期淘汰 / 超上限淘汰）
集中于本类内部；对外读接口（get / peek）不改变状态（仅惰性回收过期项，属缓存自身写职责），
pop 才是显式的一次性消费删除。避免各调用方手写 dict+expiry 重复实现（Avoid §4）并分叉 TTL。

对齐 dsh-superagent「one writer per state」/「Read queries never write」：
- 写：set / pop / 淘汰 —— 只有本类触碰内部两个 dict。
- 读：get / peek / size —— 不改变条目集（过期惰性回收除外）。

并发说明：单事件循环下这些是同步 dict 操作，协程只在 await 点切换、中途不可被打断，无真争用，
故不加锁。若将来把序列化挪进线程池，需补 threading.Lock；
若需多 worker/多进程跨进程共享本缓存，须改 Redis（见 tasks backlog B006，届时再引入持久化后端）。
"""

from typing import Any, Dict, Generic, Optional, TypeVar

import time

K = TypeVar("K")
V = TypeVar("V")


class BoundedTTLCache(Generic[K, V]):
    """有界 + TTL 的进程内缓存。单一写者：set/pop/淘汰集中在本类。"""

    def __init__(self, max_entries: int = 50, ttl_seconds: float = 600.0) -> None:
        self._max_entries = max(max_entries, 1)
        self._ttl_seconds = ttl_seconds
        self._store: Dict[K, V] = {}
        self._expiry: Dict[K, float] = {}

    def set(self, key: K, value: V) -> None:
        """写入一个条目并设置过期时间；超上限时淘汰最早的条目。"""
        now = time.time()
        self._store[key] = value
        self._expiry[key] = now + self._ttl_seconds

        if len(self._store) > self._max_entries:
            self._evict_oldest()

    def get(self, key: K) -> Optional[V]:
        """只读获取；键不存在或已过期返回 None。过期条目在此惰性回收（本类自身写职责）。"""
        expiry = self._expiry.get(key)
        if expiry is None:
            return None
        if time.time() > expiry:
            self._store.pop(key, None)
            self._expiry.pop(key, None)
            return None
        return self._store.get(key)

    def peek(self, key: K) -> Optional[V]:
        """只读窥视，不做任何淘汰删除（连过期回收都不触碰状态）。"""
        expiry = self._expiry.get(key)
        if expiry is None or time.time() > expiry:
            return None
        return self._store.get(key)

    def pop(self, key: K) -> Optional[V]:
        """一次性消费读取并删除。仅当调用方确实需要「取走」时使用。"""
        value = self._store.pop(key, None)
        if value is not None:
            self._expiry.pop(key, None)
        return value

    def clear(self) -> None:
        """清空缓存（测试/失效用）。"""
        self._store.clear()
        self._expiry.clear()

    def size(self) -> int:
        """当前条目数（可观测/压测用）。"""
        return len(self._store)

    def keys(self) -> list:
        """当前所有键（不含过期回收）。"""
        return list(self._store.keys())

    def _evict_oldest(self) -> None:
        """淘汰最早过期的条目（单一写者的淘汰职责）。"""
        oldest_id = min(self._expiry, key=self._expiry.get)
        self._store.pop(oldest_id, None)
        self._expiry.pop(oldest_id, None)