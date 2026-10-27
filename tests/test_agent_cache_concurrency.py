"""
agent 缓存并发冷启动去重测试

验证：并发 get_cached_async_agent 只 create_async_agent 一次；
失败时清 pending，不悬挂。
"""
import os
import sys
import asyncio
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


class _Counter:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def inc(self):
        with self.lock:
            self.calls += 1
            return self.calls


def test_async_concurrent_startup_single_create(monkeypatch):
    """并发首请求应对同一 name 只 create_async_agent 一次。"""
    from agent.analyst_agent import AnalystAgentFactory

    counter = _Counter()
    created = []

    async def fake_create_async_agent(self, *args, **kwargs):
        counter.inc()
        await asyncio.sleep(0.05)
        agent = object()
        created.append(agent)
        return agent

    monkeypatch.setattr(AnalystAgentFactory, "create_async_agent", fake_create_async_agent)

    factory = AnalystAgentFactory()

    async def run():
        return await asyncio.gather(
            *[factory.get_cached_async_agent("default") for _ in range(10)]
        )

    results = asyncio.run(run())
    assert counter.calls == 1, f"应当只创建 1 次，实际 {counter.calls}"
    assert all(r is created[0] for r in results)
    # 后续命中缓存，不再创建
    assert asyncio.run(factory.get_cached_async_agent("default")) is created[0]
    assert counter.calls == 1


def test_async_failure_clears_pending(monkeypatch):
    """create_async_agent 抛错时应清 pending，后续可重试。"""
    from agent.analyst_agent import AnalystAgentFactory

    counter = _Counter()

    async def failing_create(self, *args, **kwargs):
        counter.inc()
        raise RuntimeError("boom")

    async def succeeding_create(self, *args, **kwargs):
        await asyncio.sleep(0.01)
        return object()

    monkeypatch.setattr(AnalystAgentFactory, "create_async_agent", failing_create)
    factory = AnalystAgentFactory()

    async def first_try():
        try:
            await factory.get_cached_async_agent("default")
        except RuntimeError:
            pass

    asyncio.run(first_try())
    # 失败后 pending 应已清空，且不持有该 name
    assert "default" not in factory._async_agent_pending

    # 换成功创建，应能重建且 pending 干净
    monkeypatch.setattr(AnalystAgentFactory, "create_async_agent", succeeding_create)
    agent = asyncio.run(factory.get_cached_async_agent("default"))
    assert agent is not None
    assert "default" in factory._async_agent_cache  # 已入缓存
    assert "default" not in factory._async_agent_pending
    assert counter.calls == 1  # failing_create 只失败一次


def test_sync_get_cached_agent_single_create(monkeypatch):
    """同步版在多线程并发下也应只 create_agent 一次（依赖 threading.Lock）。"""
    from agent.analyst_agent import AnalystAgentFactory

    counter = _Counter()

    def fake_create_agent(self, *args, **kwargs):
        counter.inc()
        return object()

    monkeypatch.setattr(AnalystAgentFactory, "create_agent", fake_create_agent)
    factory = AnalystAgentFactory()
    factory.clear_cache()

    threads = [threading.Thread(target=lambda: factory.get_cached_agent("sync")) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter.calls == 1, f"同步并发应当只创建 1 次，实际 {counter.calls}"