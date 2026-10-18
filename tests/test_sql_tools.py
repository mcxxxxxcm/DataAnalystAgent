"""
tools/sql_tools 单元测试

覆盖 query_database 的「瞬时错误 raise / 逻辑错误 success=false」分流。
纯逻辑测试，不依赖真实数据库：monkeypatch guard_query_sql 与 db_pool.fetch。
运行：pytest tests/test_sql_tools.py（在项目根目录执行）
"""
import os
import sys
import asyncio

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


def _run(coro):
    """无 pytest-asyncio 环境下同步执行异步调用"""
    return asyncio.run(coro)


class TransientError(Exception):
    """模拟瞬时连接错误（SQLSTATE 08006 + 关键字 connection，命中 is_transient_error）"""

    sqlstate = "08006"

    def __str__(self):
        return "connection to server was lost"


class LogicError(Exception):
    """模拟逻辑错误（列不存在，非瞬时）"""

    def __str__(self):
        return 'column "sales.nope" does not exist'


def _patch_guard(monkeypatch):
    """把 guard_query_sql 换成返回合法 SQL 的替身，避免触库"""
    from tools import sql_tools

    async def _guard(query):
        return "SELECT 1", None

    monkeypatch.setattr(sql_tools, "guard_query_sql", _guard)
    return sql_tools


def test_query_database_raises_transient_error(monkeypatch):
    sql_tools = _patch_guard(monkeypatch)

    async def _fetch(*a, **k):
        raise TransientError("connection to server was lost")

    monkeypatch.setattr(sql_tools.db_pool, "fetch", _fetch)

    with pytest.raises(TransientError):
        _run(sql_tools.query_database.ainvoke({"query": "SELECT 1"}))


def test_query_database_returns_error_for_logic_error(monkeypatch):
    from tools.result_schemas import parse_tool_result

    sql_tools = _patch_guard(monkeypatch)

    async def _fetch(*a, **k):
        raise LogicError('column "sales.nope" does not exist')

    monkeypatch.setattr(sql_tools.db_pool, "fetch", _fetch)

    raw = _run(sql_tools.query_database.ainvoke({"query": "SELECT 1"}))
    payload = parse_tool_result(raw)
    assert payload["success"] is False
    assert "column_not_found" in payload["error"] or "does not exist" in payload["error"]