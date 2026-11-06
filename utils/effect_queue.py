"""
持久化 Effects 队列 + 指数退避

位置：utils/effect_queue.py
职责：迁移 dsh-superagent `Effects`（src/app/effects.ts）的句型，为「可重试的副作用」提供：
- **按 (kind,key) 幂等去重合并**：同 key 待处理时替换 payload 并立即到期（对齐 dsh "enqueuing the same key
  replaces its payload and makes it due immediately"）；
- **指数退避 + 抖动**：失败按 `base_delay * 2^(attempts)` 退避重排，达 max_attempts 记失败；
- **持久化**：可选 JSONL 落盘（effect 元数据 + payload 的 json-safe 形态），重启后可 recover，供消费方重新接线；
- **健康可观测**：pending / settled / failed 计数。

设计要点：
- 处理器按 kind 注册（`register_handler`），队列按到期顺序逐个执行（单事件循环，无锁）。
- `run_sql_durable` 是给 SQL 瞬时错误路径的便捷封装：透传到底层 `db_pool.fetch/execute`，经队列的指数退避执行，
  成功返回结果 / 终态失败抛原始异常（不吞错、不改变成败语义）。
- timeout 真正生效：处理器收到的 `timeout` 由 asyncpg `command_timeout` 兜底（agreement Avoid §5）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from core.security.sql_error import is_transient_error


@dataclass
class _Effect:
    kind: str
    key: str
    payload: Any
    max_attempts: int = 3
    base_delay: float = 1.0
    attempts: int = 0
    next_due: float = 0.0

    @property
    def _id(self) -> str:
        return f"{self.kind}:{self.key}"


class AsyncEffectQueue:
    """
    持久化 + key 幂等 + 指数退避的效果队列。

    用法：
        q = AsyncEffectQueue()
        async def handler(payload): ...
        q.register_handler("sql", handler)
        await q.enqueue("sql", key, payload, max_attempts=2, base_delay=0.01)
        await q.run_pending()
    """

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._effects: dict[str, _Effect] = {}
        self._handlers: dict[str, Callable[[Any], Awaitable[Any]]] = {}
        self._last_outcomes: dict[str, Any] = {}
        self._fail_count = 0
        self._settle_count = 0
        self._persist_path = Path(persist_path) if persist_path else None

    # ── handlers（按 kind 注册处理器）─────────────────────────
    def register_handler(self, kind: str, handler: Callable[[Any], Awaitable[Any]]) -> None:
        self._handlers[kind] = handler

    # ── enqueue（key 幂等合并）───────────────────────────────
    async def enqueue(
        self,
        kind: str,
        key: str,
        payload: Any,
        max_attempts: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        eid = f"{kind}:{key}"
        existing = self._effects.get(eid)
        if existing is not None:
            # dsh：同 key 待处理时替换 payload 并立即到期（幂等合并去重）
            existing.payload = payload
            existing.max_attempts = max_attempts
            existing.base_delay = base_delay
            existing.next_due = 0.0
        else:
            self._effects[eid] = _Effect(
                kind=kind, key=key, payload=payload,
                max_attempts=max_attempts, base_delay=base_delay, next_due=0.0,
            )
        await self._persist()

    # ── 执行──────────────────────────────────────────────────
    async def run_pending(self) -> None:
        """按到期顺序执行到期 effect；瞬时失败按指数退避重排，达 max_attempts 记失败并移出待处理。"""
        due = sorted(
            (e for e in self._effects.values() if e.next_due <= time.time()),
            key=lambda e: e.next_due,
        )
        for e in due:
            handler = self._handlers.get(e.kind)
            if handler is None:
                self._finish_failed(e, f"未注册的 effect kind: {e.kind}")
                continue
            try:
                result = await handler(e.payload)
                self._last_outcomes[e._id] = result
                self._settle_count += 1
                self._effects.pop(e._id, None)
                await self._persist()
            except Exception as exc:
                if is_transient_error(exc) and e.attempts < e.max_attempts:
                    e.attempts += 1
                    delay = e.base_delay * (2 ** (e.attempts - 1)) + random.uniform(0, e.base_delay * 0.1)
                    e.next_due = time.time() + delay
                    await asyncio.sleep(delay)
                else:
                    self._finish_failed(e, str(exc))

    async def run_effect(
        self,
        kind: str,
        key: str,
        fn: Callable[..., Awaitable[Any]],
        args: tuple = (),
        kwargs: dict = None,
        max_attempts: int = 3,
        base_delay: float = 1.0,
    ) -> Any:
        """把一次可重试调用作为单 effect 执行：成功返回结果；终态失败抛原始异常。"""
        kwargs = kwargs or {}
        e = _Effect(kind=kind, key=key, payload=None, max_attempts=max_attempts, base_delay=base_delay)
        attempts = 0
        while True:
            try:
                result = await fn(*args, **kwargs)
                self._last_outcomes[e._id] = result
                self._settle_count += 1
                return result
            except Exception as exc:
                if is_transient_error(exc) and attempts < max_attempts:
                    attempts += 1
                    delay = base_delay * (2 ** (attempts - 1)) + random.uniform(0, base_delay * 0.1)
                    await asyncio.sleep(delay)
                else:
                    self._fail_count += 1
                    raise

    def _finish_failed(self, e: _Effect, error: str) -> None:
        """瞬时重试耗尽 / 非瞬时 / 无处理器 → 记失败并移出待处理（健康计数）。"""
        self._last_outcomes[e._id] = error
        self._fail_count += 1
        self._effects.pop(e._id, None)

    # ── 可观测─────────────────────────────────────────────────
    def pending(self) -> int:
        return len(self._effects)

    def settled(self) -> int:
        return self._settle_count

    def failed(self) -> int:
        return self._fail_count

    def outcome(self, kind: str, key: str) -> Any:
        return self._last_outcomes.get(f"{kind}:{key}")

    # ── 持久化（JSONL 元数据 + payload 的 json-safe 形态）─────
    async def _persist(self) -> None:
        if self._persist_path is None:
            return
        rows = []
        for e in self._effects.values():
            row = asdict(e)
            try:
                json.dumps(row["payload"])
            except (TypeError, ValueError):
                row["payload"] = {"__non_json__": str(row["payload"])}
            rows.append(row)
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._persist_path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(self._persist_path)

    def recover(self) -> list:
        """读取持久化的待处理 effect 元数据（供消费方按 kind/key 重新接线 payload）。"""
        if self._persist_path is None or not self._persist_path.exists():
            return []
        out = []
        with open(self._persist_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out


# 全局 SQL effect 队列（供 SQL 瞬时错误路径复用；测试可替换）
_sql_queue = AsyncEffectQueue()


async def run_sql_durable(
    fn: Callable[..., Awaitable[Any]],
    *,
    key: str,
    max_retries: int,
    base_delay: float,
    args: tuple = (),
    kwargs: dict = None,
) -> Any:
    """SQL 瞬时错误路径：经队列的指数退避执行。max_retries<=0 时直接原样 await（关闭退避层）。"""
    kwargs = kwargs or {}
    if max_retries <= 0:
        return await fn(*args, **kwargs)
    return await _sql_queue.run_effect("sql_direct", key, fn, args=args, kwargs=kwargs,
                                       max_attempts=max_retries, base_delay=base_delay)


def sql_key(sql: str) -> str:
    """规范化 SQL 的稳定 key（去重/去重执行共用）。"""
    return hashlib.sha256(str(sql).strip().encode("utf-8")).hexdigest()


__all__ = ["AsyncEffectQueue", "run_sql_durable", "sql_key", "is_transient_error"]