"""
middleware/truncation 模块单元测试

覆盖工具返回载荷裁剪的核心逻辑。
condense_tool_result 为纯函数，不依赖真实数据库/Agent。
运行：pytest tests/test_truncation.py（在项目根目录执行）
"""
import os
import sys
import json

import pytest

# 保证能导入项目模块，并提供测试可用的配置环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


def make_payload(n_rows=50, cell_len=300):
    rows = [{"id": i, "name": "x" * cell_len, "v": i * 1.5} for i in range(n_rows)]
    return json.dumps({
        "success": True,
        "row_count": n_rows,
        "columns": ["id", "name", "v"],
        "data": rows,
        "execution_time": 1.23,
    })


def test_truncates_data_rows_but_keeps_key_fields():
    from middleware.truncation import condense_tool_result
    out = json.loads(condense_tool_result(make_payload(n_rows=50), max_rows=20, max_chars_per_cell=200))

    assert out["row_count"] == 50          # 保留总行数
    assert out["columns"] == ["id", "name", "v"]
    assert out["success"] is True
    assert "execution_time" in out         # 关键字段保留
    assert len(out["data"]) == 20          # 数据被截断到 20 行
    assert out["truncated"] is True
    assert out["truncated_rows"] == 30


def test_truncates_long_cells():
    from middleware.truncation import condense_tool_result
    out = json.loads(condense_tool_result(make_payload(n_rows=5), max_rows=20, max_chars_per_cell=200))
    cell = out["data"][0]["name"]
    assert cell.startswith("x" * 200)
    assert "[len 300]" in cell             # 超长单元格带长度标记


def test_small_data_not_marked_truncated():
    from middleware.truncation import condense_tool_result
    out = json.loads(condense_tool_result(make_payload(n_rows=3), max_rows=20))
    assert out["truncated"] is False
    assert len(out["data"]) == 3


def test_non_data_json_unchanged():
    from middleware.truncation import condense_tool_result
    payload = json.dumps({"a": 1, "b": [1, 2, 3]})
    assert json.loads(condense_tool_result(payload)) == {"a": 1, "b": [1, 2, 3]}


def test_long_plain_text_truncated():
    from middleware.truncation import condense_tool_result
    s = "A" * 9000
    c = condense_tool_result(s, max_content_len=8000)
    assert len(c) < 8200
    assert "[truncated" in c


def test_invalid_json_unchanged():
    from middleware.truncation import condense_tool_result
    assert condense_tool_result("{bad json") == "{bad json"


@pytest.mark.parametrize("n_bytes,n_rows", [(0, 1), (10, 5)])
def test_error_and_empty_states(n_bytes, n_rows):
    """错误载荷（error 字段）与边界行数不触发异常"""
    from middleware.truncation import condense_tool_result
    err = json.dumps({"success": False, "error": "x" * n_bytes})
    parsed_error = json.loads(condense_tool_result(err))["error"]
    if n_bytes:
        assert parsed_error.startswith("x")
    else:
        assert parsed_error == ""
    ok = json.loads(condense_tool_result(make_payload(n_rows=n_rows)))
    assert len(ok["data"]) == n_rows


def test_condense_tool_results_rebuilds_toolmessage():
    """在 LangChain 消息列表上，仅裁剪 ToolMessage，其余消息不动"""
    from langchain_core.messages import ToolMessage, HumanMessage
    from middleware.truncation import condense_tool_results

    big = json.dumps({"success": True, "row_count": 100, "columns": ["a"], "data": [{"a": i} for i in range(100)]})
    tm = ToolMessage(id="m1", tool_call_id="call_1", name="query_database", content=big)
    hm = HumanMessage(id="h1", content="你好")

    msgs = condense_tool_results([hm, tm])

    assert msgs[0] is hm                      # 非 ToolMessage 保持原引用
    m1 = msgs[1]
    assert isinstance(m1, ToolMessage)
    got = json.loads(m1.content)
    assert len(got["data"]) == 20 and got["row_count"] == 100
    assert got["truncated_rows"] == 80