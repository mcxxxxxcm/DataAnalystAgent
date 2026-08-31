"""
工具返回载荷裁剪

位置：middleware/truncation.py
职责：在把 messages 送入 LLM 之前，压缩 ToolMessage 的载荷，
只保留必要字段与关键数据，降低 token 消耗与存储膨胀（类似 Claude Code 的做法）。

说明：
- 裁剪在模型调用前（@before_model）执行，所以"刚产生的本轮工具结果"不会被自己压缩，
  而是从下一轮起被压缩 —— 跨轮压缩行为。
- 保留顶层关键字段（success/row_count/columns/error/execution_time/chart_type/
  message/image_base64(...)/table ），data 行数与单格长度按配置截断。
- 阈值集中来自 config.settings，也便于单测注入。
"""

import json
from typing import Dict, Any

from langchain_core.messages import ToolMessage

# 压缩后仍需保留的顶层字段
# 由 tools.result_schemas 的返回模型字段并集驱动（单一事实来源），
# 延迟加载以免模块导入时牵引整个 tools/DB 栈（本模块保持轻量、可单测）。
_KEEP_FIELDS: set[str] | None = None


def _keep_fields() -> set[str]:
    global _KEEP_FIELDS
    if _KEEP_FIELDS is None:
        from tools.result_schemas import RESULT_KEEP_FIELDS
        _KEEP_FIELDS = RESULT_KEEP_FIELDS
    return _KEEP_FIELDS


def truncation_settings():
    """从配置读取裁剪阈值，便于单测覆盖/传参"""
    from config.settings import get_settings
    s = get_settings()
    return {
        "max_rows": s.tool_result_max_rows,
        "max_chars_per_cell": s.tool_result_max_chars_per_cell,
        "max_content_len": s.tool_result_max_content_len,
    }


def _truncate_cell(value: Any, max_chars: int) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + f"...[len {len(value)}]"
    if isinstance(value, list):
        return [_truncate_cell(v, max_chars) for v in value]
    if isinstance(value, dict):
        return {k: _truncate_cell(v, max_chars) for k, v in value.items()}
    return value


def condense_tool_result(content: str, max_rows: int = 20,
                         max_chars_per_cell: int = 200,
                         max_content_len: int = 8000) -> str:
    """压缩单条工具返回的 JSON 载荷（或截断普通长文本）。"""
    if not isinstance(content, str):
        return content

    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        # 非 JSON：按字符上限截断
        if isinstance(content, str) and len(content) > max_content_len:
            return content[:max_content_len] + f"...[truncated total {len(content)} chars]"
        return content

    if not isinstance(payload, dict):
        # 非对象 JSON（如单个数字/字符串）也做长度兜底
        return content

    has_data = isinstance(payload.get("data"), list)
    if not has_data:
        return content

    rows = payload["data"]
    total_rows = len(rows)
    keep = rows[:max_rows]
    truncated_n = total_rows - len(keep)

    condensed = {k: v for k, v in payload.items() if k in _keep_fields()}
    # 关键字段始终保留但单格长度受限
    for k in list(condensed.keys()):
        condensed[k] = _truncate_cell(condensed[k], max_chars_per_cell)

    condensed["data"] = [_truncate_cell(row, max_chars_per_cell) for row in keep]
    if truncated_n > 0:
        condensed["truncated"] = True
        condensed["truncated_rows"] = truncated_n
        condensed["note"] = f"数据已裁剪，仅保留前 {len(keep)}/total {total_rows} 行，共裁去 {truncated_n} 行"
    else:
        condensed["truncated"] = False

    return json.dumps(condensed, ensure_ascii=False, default=str)


def condense_tool_results(messages: list) -> list:
    """
    压缩消息列表中所有 ToolMessage 的载荷，返回新列表。

    其余消息原样保留（不变更对象引用）。
    """
    settings = truncation_settings()
    max_rows = settings["max_rows"]
    max_chars = settings["max_chars_per_cell"]
    max_len = settings["max_content_len"]

    out = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and isinstance(msg.content, str):
            new_content = condense_tool_result(
                msg.content, max_rows=max_rows,
                max_chars_per_cell=max_chars, max_content_len=max_len,
            )
            if new_content == msg.content:
                out.append(msg)
            else:
                out.append(ToolMessage(
                    id=msg.id,
                    name=msg.name,
                    tool_call_id=msg.tool_call_id,
                    content=new_content,
                ))
        else:
            out.append(msg)
    return out