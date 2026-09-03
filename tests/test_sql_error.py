"""
core/security/sql_error 模块单元测试

覆盖 classify_sql_error / build_self_correction_message 的分类逻辑。
均为纯逻辑测试，不依赖真实数据库。
运行：pytest tests/test_sql_error.py（在项目根目录执行）
"""
import os
import sys

# 保证能导入项目模块，并提供测试可用的配置环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")

from core.security.sql_error import (
    classify_sql_error,
    build_self_correction_message,
)


def test_column_not_found():
    info = classify_sql_error('column "sales.money2" does not exist')
    assert info["code"] == "column_not_found"
    assert "列" in info["suggestion"]


def test_relation_not_found():
    info = classify_sql_error('relation "sale" does not exist')
    assert info["code"] == "relation_not_found"
    assert "表" in info["suggestion"]


def test_ambiguous_column():
    info = classify_sql_error('column reference "id" is ambiguous')
    assert info["code"] == "ambiguous_column"
    assert "别名" in info["suggestion"] or "限定" in info["suggestion"]


def test_function_not_found():
    info = classify_sql_error('function sum(x, y) does not exist')
    assert info["code"] == "function_not_found"


def test_syntax_error():
    info = classify_sql_error('syntax error at or near "select"')
    assert info["code"] == "syntax_error"


def test_division_by_zero():
    info = classify_sql_error('division by zero')
    assert info["code"] == "division_by_zero"
    assert "NULLIF" in info["suggestion"]


def test_query_timeout():
    info = classify_sql_error('canceling statement due to statement timeout')
    assert info["code"] == "query_timeout"


def test_group_by_error():
    info = classify_sql_error('column "sales.region" must appear in the GROUP BY clause')
    assert info["code"] == "group_by_error"


def test_unknown_error_falls_back():
    info = classify_sql_error("some mysterious error without a known signature 12345")
    assert info["code"] == "unknown"


def test_empty_error_falls_back():
    info = classify_sql_error("")
    assert info["code"] == "unknown"


def test_build_self_correction_message_contains_parts():
    msg = build_self_correction_message('column "region_code" does not exist')
    assert msg.startswith("[column_not_found]")
    assert "修复建议" in msg
    assert "column" in msg  # 原始错误仍保留