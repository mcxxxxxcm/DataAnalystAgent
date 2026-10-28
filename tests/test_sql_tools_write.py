"""
query_database 写分派测试

验证：
- 写操作（INSERT/UPDATE/DELETE）走 db_pool.execute、解析受影响行数、写后失效 schema 缓存；
- 写结果不入 result_store（写结果不适合作图表数据源）；
- SELECT 路径仍走 db_pool.fetch + set_result，不受影响。
通过 monkeypatch 替换守卫/连接池/缓存，纯单测不依赖真实数据库。
运行：pytest tests/test_sql_tools_write.py
"""
import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")

from core.database import db_pool, schema_manager
import tools.sql_tools as st
from tools.result_schemas import parse_tool_result
from tools.sql_tools import _is_write_dml, _parse_affected_rows


# ---------------- 纯函数 ----------------

def test_is_write_dml_detects_types():
    assert _is_write_dml("INSERT INTO t (a) VALUES (1)") == "INSERT"
    assert _is_write_dml("  DELETE  FROM t WHERE id=1") == "DELETE"
    assert _is_write_dml("update t set a=1 where id=1") == "UPDATE"
    assert _is_write_dml("SELECT * FROM t") == ""
    assert _is_write_dml("") == ""


def test_parse_affected_rows():
    assert _parse_affected_rows("INSERT 0 1") == 1
    assert _parse_affected_rows("DELETE 3") == 3
    assert _parse_affected_rows("UPDATE 2") == 2
    assert _parse_affected_rows("INSERT 0 0") == 0
    assert _parse_affected_rows("") == 0
    assert _parse_affected_rows(None) == 0


# ---------------- 写分派行为 ----------------

def test_write_dispatch_executes_clears_cache_not_in_store(monkeypatch):
    """写操作应执行 db_pool.execute、清 schema 缓存、且绝不写 result_store。"""
    async def fake_execute(sql, *, timeout=None):
        return "INSERT 0 1"
    cleared = []
    monkeypatch.setattr(db_pool, "execute", fake_execute)
    monkeypatch.setattr(schema_manager, "clear_cache", lambda *a, **k: cleared.append(1))
    async def _guard(query, **k):
        return query, None
    monkeypatch.setattr(st, "guard_query_sql", _guard)

    def deny_set_result(*a, **k):
        raise AssertionError("写结果不应写入 result_store")
    monkeypatch.setattr(st, "set_result", deny_set_result)

    out = parse_tool_result(asyncio.run(st.query_database.ainvoke({"query": "INSERT INTO sales (region) VALUES ('n')"})))
    assert out["success"] is True
    assert out["row_count"] == 1
    assert out["data"] == [{"操作": "INSERT", "受影响行数": 1}]
    assert out["columns"] == ["操作", "受影响行数"]
    assert cleared, "写后应清除 schema 缓存"


def test_write_delete_returns_rows(monkeypatch):
    async def fake_execute(sql, *, timeout=None):
        return "DELETE 3"
    monkeypatch.setattr(db_pool, "execute", fake_execute)
    monkeypatch.setattr(schema_manager, "clear_cache", lambda *a, **k: None)
    async def _guard(query, **k):
        return query, None
    monkeypatch.setattr(st, "guard_query_sql", _guard)
    monkeypatch.setattr(st, "set_result", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应入 store")))

    out = parse_tool_result(asyncio.run(st.query_database.ainvoke({"query": "DELETE FROM sales WHERE id <= 3"})))
    assert out["success"] is True
    assert out["row_count"] == 3
    assert out["data"][0]["受影响行数"] == 3


def test_select_path_unchanged(monkeypatch):
    """SELECT 路径仍走 fetch + set_result，返回查询结果。"""
    rows = [{"region": "n", "revenue": 10}]
    async def fake_fetch(sql, **k):
        return rows
    monkeypatch.setattr(db_pool, "fetch", fake_fetch)
    async def _guard(query, **k):
        return query, None
    monkeypatch.setattr(st, "guard_query_sql", _guard)
    monkeypatch.setattr(st, "set_result", lambda columns, data: "rid-123")

    out = parse_tool_result(asyncio.run(st.query_database.ainvoke({"query": "SELECT region, revenue FROM sales"})))
    assert out["success"] is True
    assert out["data"] == [{"region": "n", "revenue": 10}]
    assert out["result_id"] == "rid-123"
    assert out["row_count"] == 1