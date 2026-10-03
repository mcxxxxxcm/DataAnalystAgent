"""
图表 spec 构建器单测：build_echarts_option
"""
import json

from utils.chart_spec import build_echarts_option, recommend_chart_type

COLUMNS = ["region", "revenue"]
ROWS = [
    {"region": "华东", "revenue": 100},
    {"region": "华南", "revenue": 80},
    {"region": "华北", "revenue": 60},
    {"region": "西南", "revenue": 40},
]


def _assert_option_shape(built, chart_type):
    assert built["success"] is True
    assert built["chart_type"] == chart_type
    assert built["error"] == ""
    opt = built["option"]
    # 必须可被 JSON 序列化（前端 ECharts 消费）
    json.dumps(opt)
    return opt


def test_bar_option_has_dataset_source_and_encode():
    built = build_echarts_option("bar", COLUMNS, ROWS, "region", "revenue")
    opt = _assert_option_shape(built, "bar")
    assert opt["series"][0]["type"] == "bar"
    assert opt["dataset"]["source"][0] == COLUMNS
    assert len(opt["dataset"]["source"]) == len(ROWS) + 1


def test_pie_option_builds_name_value_pairs():
    built = build_echarts_option("pie", COLUMNS, ROWS, "region", "revenue")
    opt = _assert_option_shape(built, "pie")
    assert opt["series"][0]["type"] == "pie"
    names = [d["name"] for d in opt["series"][0]["data"]]
    assert names == ["华东", "华南", "华北", "西南"]


def test_line_scatter_types():
    assert build_echarts_option("line", COLUMNS, ROWS, "region", "revenue")["success"]
    built = build_echarts_option("scatter", COLUMNS, ROWS, "region", "revenue")
    assert built["chart_type"] == "scatter"
    assert built["option"]["series"][0]["type"] == "scatter"


def test_unsupported_chart_type_rejected():
    built = build_echarts_option("donut", COLUMNS, ROWS, "region", "revenue")
    assert built["success"] is False
    assert "不支持" in built["error"]


def test_missing_field_gives_exact_error_with_valid_columns():
    built = build_echarts_option("bar", COLUMNS, ROWS, "sales", "revenue")
    assert built["success"] is False
    assert "region" in built["error"]
    assert "revenue" in built["error"]


def test_empty_rows_rejected():
    built = build_echarts_option("bar", COLUMNS, [], "region", "revenue")
    assert built["success"] is False


def test_auto_recommend_bar_for_low_cardinality_category():
    assert recommend_chart_type(COLUMNS, ROWS, "region", "revenue") == "bar"


def test_auto_recommend_line_for_many_numeric_x():
    rows = [{"t": i, "v": float(i)} for i in range(20)]
    assert recommend_chart_type(["t", "v"], rows, "t", "v") == "line"