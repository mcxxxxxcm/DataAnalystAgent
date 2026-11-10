"""
滑动窗口限流 / 配额（backlog B010）

位置：core/security/rate_limit.py
职责：按来源/token 做滑动窗口限流，防滥用。有界：key 上限 + 惰性清过期时间戳。

默认关闭：enable_rbac=False 或未配置 rbac_rate_limit 时不实例化，逻辑完全旁路。
"""

from __future__ import annotations

import re
import time
from collections import deque
from typing import Deque, Dict, Optional


class SlidingWindowLimiter:
    """滑动窗口限流器。allow(key) 返回 True/False：窗口内未超限则放行并记账。"""

    def __init__(self, limit: int, window_seconds: float, max_keys: int = 4096) -> None:
        self._limit = max(limit, 1)
        self._window_seconds = max(window_seconds, 0.1)
        self._max_keys = max(max_keys, 1)
        self._buckets: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> bool:
        """限下放行（并记入），超限拒绝。空/未知 key 不记账（不要误伤）。
        并发：同步逻辑，单事件循环内安全；多线程进调用方自行加锁。"""
        key = str(key or "").strip()
        if not key:
            return True
        now = time.time()
        dq = self._buckets.setdefault(key, deque())
        # 过期时间戳惰性移除
        while dq and now - dq[0] >= self._window_seconds:
            dq.popleft()
        if len(dq) >= self._limit:
            return False
        dq.append(now)
        if len(self._buckets) > self._max_keys:
            self._trim(now)
        return True

    def _trim(self, now: float) -> None:
        """超过 key 上限时，优先清掉已无活跃窗口的 key。"""
        for k in [k for k, dq in self._buckets.items() if not dq]:
            del self._buckets[k]
        # 仍超则删最早写入的 key
        while len(self._buckets) > self._max_keys:
            oldest = next(iter(self._buckets))
            del self._buckets[oldest]


def parse_rate_limit(spec: Optional[str]) -> Optional[SlidingWindowLimiter]:
    """解析 "N/s|m|h|d"（如 "10/min"）。非法/空返回 None（不启用）。"""
    if not spec or not str(spec).strip():
        return None
    m = re.match(r"^\s*(\d+)\s*/\s*(\w+)\s*$", str(spec))
    if not m:
        return None
    limit = int(m.group(1))
    unit = m.group(2).lower()
    seconds = {"s": 1, "sec": 1, "second": 1,
               "m": 60, "min": 60, "minute": 60,
               "h": 3600, "hour": 3600,
               "d": 86400, "day": 86400}.get(unit)
    if seconds is None or limit <= 0:
        return None
    return SlidingWindowLimiter(limit=limit, window_seconds=float(seconds))