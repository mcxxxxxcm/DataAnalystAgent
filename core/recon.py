"""
模型视图可重建不变量（M1）核心模块

位置：core/recon.py（内部能力，不暴露给 LLM）
职责：提供**确定性**重建函数，把「会话事件序列」编排成 LangChain 消息列表，
使「发给模型的完整消息序列」可由会话日志重建（Model-visible ⟺ logged）。

本模块是纯函数、无 DB / 无 LLM，可用 DB/LLM-free 断言回归覆盖。

Event schema（声明式会话trace，单一数据源）：
    {"type": "system", "content": str}                              -> SystemMessage
    {"type": "user", "content": str}                                -> HumanMessage
    {"type": "assistant_tool_calls", "calls": [{"id","name","args"}],
     "content": str|None}                                           -> AIMessage(tool_calls)
    {"type": "tool_result", "tool_call_id": str, "tool": str,
     "content": str|None}                                           -> ToolMessage(model_view)
    {"type": "resume", "decisions": [...]}                          -> HumanMessage(Command resume)
    {"type": "summary", "content": str}                             -> SystemMessage(长上下文摘要)

顺序契约：按事件给定的先后顺序产出消息，不做重排；tool_result 用 tool_call_id
与 assistant_tool_calls 配对（配对失败仍保留 ToolMessage，配对仅作信息校验）。

未知事件类型：默认抛 ValueError（fail loud，对齐 DSH「misconfiguration fails loud」）。
"""

from typing import Dict, Any
import json

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

# 未知事件类型交由此处理（fail loud）
UNSUPPORTED_EVENT_MSG = "unsupported recon event type: {0}"


def _make_ai_message(event: Dict[str, Any]) -> AIMessage:
    calls = event.get("calls") or []
    tool_calls = [
        {"id": c.get("id"), "name": c.get("name"), "args": c.get("args") or {}}
        for c in calls
    ]
    return AIMessage(content=event.get("content") or "", tool_calls=tool_calls)


def _make_tool_message(event: Dict[str, Any]) -> ToolMessage:
    # content 即 model_view（与送入 LLM 同阈值裁剪后的内容）
    return ToolMessage(
        tool_call_id=event.get("tool_call_id") or "",
        name=event.get("tool"),
        content=event.get("content") or "",
    )


def _make_human_message(event: Dict[str, Any]) -> HumanMessage:
    decisions = event.get("decisions")
    if decisions is not None:
        # LangChain 消息 content 仅接受 str / list，故决策结构序列化为字符串，
        # 结构化副本保留在 additional_kwargs 便于审计。
        payload = {"type": "decisions", "decisions": decisions}
        return HumanMessage(
            content=json.dumps(payload, ensure_ascii=False),
            additional_kwargs={"command": {"type": "resume"}, "resume": payload},
        )
    return HumanMessage(content=event.get("content") or "")


def reconstruct_model_messages(events: list) -> list[BaseMessage]:
    """
    把会话事件序列确定性编排成 LangChain 消息列表。

    参数:
        events: 有序的声明式会话事件列表（见模块 docstring 的 schema）。

    返回:
        按事件顺序产出的消息列表，作为「发给模型的消息序列」的可重建表示。

    异常:
        ValueError: 遇到未知事件类型（fail loud）。
    """
    out: list[BaseMessage] = []
    for ev in events:
        etype = ev.get("type") if isinstance(ev, dict) else None
        if etype == "system":
            out.append(SystemMessage(content=ev.get("content") or ""))
        elif etype == "summary":
            out.append(SystemMessage(content=ev.get("content") or ""))
        elif etype == "user":
            out.append(HumanMessage(content=ev.get("content") or ""))
        elif etype == "resume":
            out.append(_make_human_message(ev))
        elif etype == "assistant_tool_calls":
            out.append(_make_ai_message(ev))
        elif etype == "tool_result":
            out.append(_make_tool_message(ev))
        else:
            raise ValueError(UNSUPPORTED_EVENT_MSG.format(etype))
    return out


def session_events_from_tool_records(records: list) -> list:
    """
    把工具调用日志记录（如 JSONL 中按会话归集的记录）转成 tool_result 事件。

    输入应保持追加时序（append-only），这里直接按输入顺序产出，不做重排。

    参数:
        records: 每个含 tool_name / model_view / record_id / timestamp 的 dict。

    返回:
        tool_result 事件列表，可被 reconstruct_model_messages 消费。
        （仅产出工具视图部分；assistant_tool_calls 需调用方补全，才能构成完整会话。）
    """
    return [
        {
            "type": "tool_result",
            "tool_call_id": _synthetic_tool_call_id(rec),
            "tool": rec.get("tool_name"),
            "content": rec.get("model_view"),
        }
        for rec in records
    ]


def _synthetic_tool_call_id(rec: dict) -> str:
    return "recon-" + (rec.get("record_id") or "")