"""
模型视图可重建不变量（M1）——core/recon 单元测试

覆盖重建顺序、配对、忠实性(与送入LLM同阈值condense)、HITL resume、summary、鲁棒性。
全 DB/LLM-free。
运行：pytest tests/test_recon.py -q（在项目根目录执行）
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from core.recon import (
    reconstruct_model_messages,
    session_events_from_tool_records,
)


def make_tool_payload(n_rows=50):
    return json.dumps({
        "success": True,
        "row_count": n_rows,
        "columns": ["id", "name"],
        "data": [{"id": i, "name": "x" * 300} for i in range(n_rows)],
    })


def test_basic_round_ordering_and_pairing():
    events = [
        {"type": "system", "content": "你是数据分析助手"},
        {"type": "user", "content": "查本月销量"},
        {"type": "assistant_tool_calls", "calls": [
            {"id": "call_1", "name": "query_database", "args": {"sql": "SELECT 1"}},
        ]},
        {"type": "tool_result", "tool_call_id": "call_1", "tool": "query_database",
         "content": make_tool_payload()},
        {"type": "user", "content": "再画个图"},
    ]
    msgs = reconstruct_model_messages(events)

    assert [type(m) for m in msgs] == [
        SystemMessage, HumanMessage, AIMessage, ToolMessage, HumanMessage,
    ]

    # system / user content 原样
    assert msgs[0].content == "你是数据分析助手"
    assert msgs[1].content == "查本月销量"
    # AIMessage 带工具调用
    assert msgs[2].tool_calls[0]["id"] == "call_1"
    assert msgs[2].tool_calls[0]["name"] == "query_database"
    # ToolMessage 与 AIMessage 的 tool_call_id 配对
    assert msgs[3].tool_call_id == msgs[2].tool_calls[0]["id"]
    assert msgs[3].name == "query_database"


def test_multiple_tool_rounds_do_not_interleave():
    events = [
        {"type": "user", "content": "q"},
        {"type": "assistant_tool_calls", "calls": [{"id": "c1", "name": "get_relevant_schemas", "args": {}}]},
        {"type": "tool_result", "tool_call_id": "c1", "tool": "get_relevant_schemas", "content": "a"},
        {"type": "assistant_tool_calls", "calls": [{"id": "c2", "name": "query_database", "args": {}}]},
        {"type": "tool_result", "tool_call_id": "c2", "tool": "query_database", "content": "b"},
    ]
    msgs = reconstruct_model_messages(events)
    pairings = [(m.tool_call_id, m.name) for m in msgs if isinstance(m, ToolMessage)]
    assert pairings == [("c1", "get_relevant_schemas"), ("c2", "query_database")]


def test_model_view_faithful_to_condense_pipeline():
    """忠实性：重建的 ToolMessage(content) 与送入 LLM 的 condense 结果一致."""
    from middleware.truncation import condense_tool_result, truncation_settings

    raw = make_tool_payload(n_rows=50)
    s = truncation_settings()
    expected = condense_tool_result(
        raw,
        max_rows=s["max_rows"],
        max_chars_per_cell=s["max_chars_per_cell"],
        max_content_len=s["max_content_len"],
    )

    events = [
        {"type": "assistant_tool_calls", "calls": [{"id": "c", "name": "query_database", "args": {}}]},
        {"type": "tool_result", "tool_call_id": "c", "tool": "query_database", "content": expected},
    ]
    msgs = reconstruct_model_messages(events)

    tm = msgs[-1]
    assert isinstance(tm, ToolMessage)
    assert tm.content == expected
    assert json.loads(tm.content)["row_count"] == 50     # 保留总行数
    assert len(json.loads(tm.content)["data"]) == s["max_rows"]  # 数据被裁剪成 max_rows


def test_hitl_resume_becomes_human_message():
    events = [
        {"type": "assistant_tool_calls", "calls": [{"id": "c", "name": "query_database", "args": {}}]},
        {"type": "resume", "decisions": [{"type": "approve"}]},
    ]
    msgs = reconstruct_model_messages(events)

    resume = msgs[-1]
    assert isinstance(resume, HumanMessage)
    # content 为决策 JSON 序列化；结构化副本保留于 additional_kwargs
    assert json.loads(resume.content)["decisions"] == [{"type": "approve"}]
    assert resume.additional_kwargs.get("command", {}).get("type") == "resume"
    assert resume.additional_kwargs.get("resume") == {
        "type": "decisions", "decisions": [{"type": "approve"}],
    }


def test_summary_becomes_system_message():
    events = [
        {"type": "user", "content": "q1"},
        {"type": "summary", "content": "早前已浓缩为：本月销量X"},
    ]
    msgs = reconstruct_model_messages(events)
    assert [type(m) for m in msgs] == [HumanMessage, SystemMessage]
    assert msgs[1].content == "早前已浓缩为：本月销量X"


def test_unsupported_event_type_fails_loud():
    with pytest.raises(ValueError):
        reconstruct_model_messages([{"type": "no_such_type"}])


def test_tool_result_with_unknown_call_id_still_emitted():
    # 配对失败不丢弃 ToolMessage（LangChain 中 ToolMessage 独立存在）
    events = [
        {"type": "tool_result", "tool_call_id": "ghost", "tool": "query_database", "content": "x"},
    ]
    msgs = reconstruct_model_messages(events)
    assert len(msgs) == 1
    assert isinstance(msgs[0], ToolMessage)
    assert msgs[0].tool_call_id == "ghost"


def test_session_events_from_tool_records_preserves_order():
    records = [
        {"tool_name": "get_relevant_schemas", "model_view": "s", "record_id": "r1", "timestamp": "2026-11-04T00:00:01"},
        {"tool_name": "query_database", "model_view": "q", "record_id": "r2", "timestamp": "2026-11-04T00:00:02"},
    ]
    events = session_events_from_tool_records(records)

    # 事件可被重建函数消费
    msgs = reconstruct_model_messages(events)
    assert [type(m) for m in msgs] == [ToolMessage, ToolMessage]
    assert msgs[0].name == "get_relevant_schemas"
    assert msgs[1].name == "query_database"
    # 输入顺序保持
    assert [e["tool_call_id"] for e in events] == ["recon-r1", "recon-r2"]


def test_non_dict_event_fails_loud():
    with pytest.raises(ValueError):
        reconstruct_model_messages(["not-a-dict"])


def test_mixed_full_session_reconstructs_all_types():
    events = [
        {"type": "system", "content": "sys"},
        {"type": "user", "content": "u1"},
        {"type": "assistant_tool_calls", "calls": [{"id": "c", "name": "query_database", "args": {}}]},
        {"type": "tool_result", "tool_call_id": "c", "tool": "query_database", "content": "{"},
        {"type": "resume", "decisions": [{"type": "approve"}]},
        {"type": "summary", "content": "s1"},
    ]
    msgs = reconstruct_model_messages(events)
    assert [type(m) for m in msgs] == [
        SystemMessage, HumanMessage, AIMessage, ToolMessage, HumanMessage, SystemMessage,
    ]