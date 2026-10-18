"""
core/database/schema 缓存 TTL 单元测试

验证 get_table_schema 的缓存过期判断用 total_seconds()（修正 timedelta.seconds 回绕）。
纯逻辑测试：直接向全局 schema_manager 注入 _cache/_cache_time，monkeypatch db_pool.fetch/fetchrow。
运行：pytest tests/test_schema_cache.py（在项目根目录执行）
"""
import os
import sys
import asyncio
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


def _run(coro):
    """无 pytest-asyncio 环境下同步执行异步调用"""
    return asyncio.run(coro)


def _make_schema(table_name):
    """构造一个最小 TableSchema 用于缓存注入"""
    from core.database.schema import TableSchema, ColumnInfo
    return TableSchema(
        table_name=table_name,
        columns=[ColumnInfo(name="id", data_type="integer", is_nullable=False)],
        primary_keys=["id"],
        foreign_keys=[],
        row_count=100,
    )


@pytest.fixture
def _patch_db(monkeypatch):
    """让 db_pool.fetch/fetchrow 记录调用次数并返回最小结构，避免真实触库"""
    import core.database.pool as pool

    called = {"n": 0}

    async def _fetch(*a, **k):
        called["n"] += 1
        return []

    async def _fetchrow(*a, **k):
        called["n"] += 1
        return None

    monkeypatch.setattr(pool.db_pool, "fetch", _fetch)
    monkeypatch.setattr(pool.db_pool, "fetchrow", _fetchrow)
    return called


def test_cache_expired_after_one_day_refetches(_patch_db):
    from core.database import schema_manager

    table = "sales"
    schema_manager._cache[table] = _make_schema(table)
    # 关键：超过 1 天 → timedelta.seconds 会回绕为 10，只有 total_seconds() 才能判过期
    schema_manager._cache_time[table] = datetime.now() - timedelta(days=1, seconds=10)

    try:
        _run(schema_manager.get_table_schema(table))
        assert _patch_db["n"] > 0, "超过 TTL 应重新查库，而非命中缓存"
    finally:
        schema_manager.clear_cache(table)


def test_cache_fresh_within_ttl_does_not_refetch(_patch_db):
    from core.database import schema_manager

    table = "sales"
    schema_manager._cache[table] = _make_schema(table)
    schema_manager._cache_time[table] = datetime.now() - timedelta(seconds=10)

    try:
        result = _run(schema_manager.get_table_schema(table))
        assert _patch_db["n"] == 0, "TTL 内应命中缓存，不做任何查询"
        assert result is schema_manager._cache[table]
    finally:
        schema_manager.clear_cache(table)