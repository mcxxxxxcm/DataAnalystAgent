"""
tools.boundaries 边界层 + tools 权限子集单元测试

均为纯逻辑测试，不依赖真实数据库、不依赖 pytest-asyncio。
通过 monkeypatch 把 schema_manager.list_tables 固定为白名单，避免触发数据库连接。
运行：pytest tests/test_tool_boundaries.py（在项目根目录执行）
"""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


def _run(coro, *args, **kwargs):
    """在无 pytest-asyncio 环境下同步执行异步副作用函数"""
    return asyncio.run(coro(*args, **kwargs))


@pytest.fixture
def allowed_tables(monkeypatch):
    """把 schema_manager.list_tables 固定为白名单 ['sales','orders']"""
    from tools import boundaries

    async def _list():
        return ["sales", "orders"]

    monkeypatch.setattr(boundaries.schema_manager, "list_tables", _list)
    return ["sales", "orders"]


# ---------------- guard_query_sql ----------------

def test_safe_select_passes(allowed_tables):
    from tools.boundaries import guard_query_sql
    sql, error = _run(guard_query_sql, "SELECT name FROM sales")
    assert error is None
    assert "SELECT" in sql.upper()


def test_drop_rejected(allowed_tables):
    from tools.boundaries import guard_query_sql
    _, error = _run(guard_query_sql, "DROP TABLE sales")
    assert error is not None
    assert "校验失败" in error


def test_write_rejected_when_disabled(allowed_tables):
    # 注入 enable_write=False 的校验器，保证断言不受运行时 .env 配置影响
    from core.security.sql_validator import SQLValidator
    from tools.boundaries import guard_query_sql
    write_disabled_validator = SQLValidator(max_rows=100, enable_write=False, timeout=30)
    _, error = _run(guard_query_sql, "DELETE FROM sales WHERE id = 1",
                    validator=write_disabled_validator)
    assert error is not None


def test_write_allowed_when_enabled(allowed_tables):
    # 注入 enable_write=True 的校验器：写操作放行，仅做清理/表名校验
    from core.security.sql_validator import SQLValidator
    from tools.boundaries import guard_query_sql
    write_enabled_validator = SQLValidator(max_rows=100, enable_write=True, timeout=30)
    sql, error = _run(guard_query_sql, "DELETE FROM sales WHERE id = 1",
                      validator=write_enabled_validator)
    assert error is None
    assert "sales" in sql


def test_system_table_rejected(allowed_tables):
    from tools.boundaries import guard_query_sql
    _, error = _run(guard_query_sql, "SELECT * FROM checkpoints")
    assert error is not None
    assert "不允许的表" in error


def test_multi_statement_rejected(allowed_tables):
    from tools.boundaries import guard_query_sql
    _, error = _run(guard_query_sql, "SELECT * FROM sales; DROP TABLE orders")
    assert error is not None


def test_limit_auto_injected(allowed_tables):
    from tools.boundaries import guard_query_sql
    sql, error = _run(guard_query_sql, "SELECT * FROM sales")
    assert error is None
    assert "LIMIT" in sql.upper()


def test_forbidden_function_rejected(allowed_tables):
    from tools.boundaries import guard_query_sql
    _, error = _run(guard_query_sql, "SELECT pg_read_file('/etc/passwd')")
    assert error is not None


# ---------------- extract_sql_tables ----------------

def test_extract_sql_tables_skips_system():
    from tools.boundaries import extract_sql_tables
    sql = "SELECT a.id FROM sales a JOIN orders b ON a.id = b.sales_id"
    tables = extract_sql_tables(sql)
    assert "sales" in tables
    assert "orders" in tables
    assert "checkpoints" not in extract_sql_tables("SELECT * FROM checkpoints")


# ---------------- is_allowed_table ----------------

def test_is_allowed_table_ok(allowed_tables):
    from tools.boundaries import is_allowed_table
    assert _run(is_allowed_table, "sales") == "sales"


def test_is_allowed_table_rejects_injection(allowed_tables):
    from tools.boundaries import is_allowed_table
    with pytest.raises(ValueError):
        _run(is_allowed_table, "sales; DROP TABLE orders")


def test_is_allowed_table_rejects_missing(allowed_tables):
    from tools.boundaries import is_allowed_table
    with pytest.raises(ValueError):
        _run(is_allowed_table, "nope")


def test_is_allowed_table_rejects_system(allowed_tables):
    from tools.boundaries import is_allowed_table
    with pytest.raises(ValueError):
        _run(is_allowed_table, "checkpoints")


# ---------------- 工具权限子集 ----------------

def test_read_only_excludes_export_and_custom_chart():
    from tools import get_enabled_tools
    tools = get_enabled_tools("read_only")
    names = {t.name for t in tools}
    assert "export_result" not in names
    assert "create_custom_chart" not in names
    assert "query_database" in names


def test_query_only_is_sql_tools():
    from tools import get_enabled_tools
    tools = get_enabled_tools("query_only")
    names = {t.name for t in tools}
    assert names == {"query_database", "list_tables", "get_table_schema",
                     "get_sample_data", "get_relevant_schemas"}


def test_full_has_all():
    from tools import get_enabled_tools, ALL_TOOLS
    full_names = {t.name for t in get_enabled_tools("full")}
    assert full_names == {t.name for t in ALL_TOOLS}


def test_unknown_scope_falls_back_to_full():
    from tools import get_enabled_tools, ALL_TOOLS
    names = {t.name for t in get_enabled_tools("bogus")}
    assert names == {t.name for t in ALL_TOOLS}