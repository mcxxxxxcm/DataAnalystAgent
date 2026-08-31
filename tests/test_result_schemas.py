"""
tools/result_schemas 模块单元测试

运行：pytest tests/test_result_schemas.py（在项目根目录执行）
"""
import os
import sys
import json

# 保证能导入项目模块，并提供测试可用的配置环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")

from tools.result_schemas import (
    QueryResult, ChartResult, StatisticalSummaryResult,
    DataProfileResult, ExportResult,
    RESULT_SCHEMAS, RESULT_KEEP_FIELDS,
    dump_result, parse_tool_result,
)


# ==================== dump_result / 模型 ====================

def test_dump_result_round_trips():
    qr = QueryResult(success=True, data=[{"a": 1}], row_count=1, columns=["a"], execution_time=1.5)
    d = json.loads(dump_result(qr))
    assert d["success"] is True
    assert d["row_count"] == 1
    assert d["columns"] == ["a"]
    assert d["data"] == [{"a": 1}]


def test_result_models_have_defaults_for_partial_builds():
    # 错误/空结果用默认值即可构造，字段形状保持一致
    cr = ChartResult(success=False, error="数据为空")
    d = json.loads(dump_result(cr))
    assert d["error"] == "数据为空"
    assert d["chart_type"] == "" and d["message"] == ""

    sr = StatisticalSummaryResult(success=False, error="boom")
    sd = json.loads(dump_result(sr))
    assert sd["success"] is False and sd["columns"] == {}


# ==================== parse_tool_result ====================

def test_parse_str_json():
    assert parse_tool_result('{"image_base64":"x","chart_type":"bar"}') == {
        "image_base64": "x", "chart_type": "bar"
    }


def test_parse_dict_passthrough():
    assert parse_tool_result({"image_base64": "x"}) == {"image_base64": "x"}


def test_parse_content_block_list():
    assert parse_tool_result([{"type": "text", "text": '{"chart_type":"line"}'}]) == {"chart_type": "line"}


def test_parse_non_json_returns_none():
    assert parse_tool_result("{bad json") is None
    assert parse_tool_result("plain text") is None


def test_parse_invalid_types_returns_none():
    assert parse_tool_result(123) is None
    assert parse_tool_result(None) is None
    assert parse_tool_result("[1,2,3]") is None  # 非对象 JSON


def test_parse_plain_string_returns_none():
    # 非 JSON 的普通文本不应被当作 dict 返回
    assert parse_tool_result("你好，这是一句回答") is None


# ==================== 注册表 / KEEP_FIELDS ====================

def test_reserved_tool_models_registered():
    assert RESULT_SCHEMAS["query_database"] is QueryResult
    assert RESULT_SCHEMAS["create_chart"] is ChartResult
    assert RESULT_SCHEMAS["statistical_summary"] is StatisticalSummaryResult
    assert RESULT_SCHEMAS["data_profile"] is DataProfileResult
    assert RESULT_SCHEMAS["export_result"] is ExportResult


def test_keep_fields_derived_from_schemas():
    # 由各模型字段推导，天然覆盖既有裁剪关键字段
    for f in ("success", "row_count", "columns", "execution_time",
              "chart_type", "message", "table", "image_base64"):
        assert f in RESULT_KEEP_FIELDS
    assert "chart_id" in RESULT_KEEP_FIELDS  # 仅存在于 image_base64 前缀，需显式保留