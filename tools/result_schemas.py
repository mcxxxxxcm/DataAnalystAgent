"""
工具返回结构与解析

位置：tools/result_schemas.py
职责：作为所有工具返回结构的单一事实来源，统一：
1. 返回 Pydantic 模型（每个工具的输出契约）
2. dump_result() —— 统一序列化为 JSON 字符串（ToolMessage.content 载体）
3. parse_tool_result() —— 健壮反序列化，接受 str / dict / 内容块 list
4. RESULT_KEEP_FIELDS —— 供裁剪中间件复用的关键字段集（避免硬编码漂移）

约束说明：
- LangChain 的 ToolMessage.content 必须是 str，故工具仍返回规范化 JSON 字符串。
- 下游（裁剪、路由）统一经 parse_tool_result 解析，不再散落 json.loads。
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 返回模型 ====================

class QueryResult(BaseModel):
    """数据库查询结果"""
    success: bool
    data: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    columns: List[str] = Field(default_factory=list)
    error: str = ""
    execution_time: float = 0.0


class ChartResult(BaseModel):
    """图表生成结果"""
    success: bool
    chart_type: str = ""
    image_base64: str = ""
    message: str = ""
    error: str = ""


class StatisticalSummaryResult(BaseModel):
    """统计摘要结果"""
    success: bool
    table: str = ""
    columns: Dict[str, Any] = Field(default_factory=dict)
    row_count_sampled: int = 0
    note: Optional[str] = None
    execution_time: float = 0.0
    error: str = ""


class DataProfileResult(BaseModel):
    """数据质量探查结果"""
    success: bool
    table: str = ""
    row_count: int = 0
    duplicate_ratio: float = 0.0
    columns: Dict[str, Any] = Field(default_factory=dict)
    execution_time: float = 0.0
    error: str = ""


class ExportResult(BaseModel):
    """导出结果"""
    success: bool
    file_id: str = ""
    filename: str = ""
    row_count: int = 0
    download_url: str = ""
    execution_time: float = 0.0
    error: str = ""


# ==================== 工具名 → 返回模型 注册表 ====================

RESULT_SCHEMAS: Dict[str, type[BaseModel]] = {
    "query_database": QueryResult,
    "create_chart": ChartResult,
    "create_custom_chart": ChartResult,
    "statistical_summary": StatisticalSummaryResult,
    "data_profile": DataProfileResult,
    "export_result": ExportResult,
}

# 关键字段并集（来自各模型字段名）∪ 保留 chart_id（仅存在于 image_base64 前缀，不在任一模型）
_RESULT_MODEL_FIELDS = {
    field_name
    for model_cls in RESULT_SCHEMAS.values()
    for field_name in model_cls.model_fields
}
RESULT_KEEP_FIELDS: set[str] = _RESULT_MODEL_FIELDS | {"chart_id"}


# ==================== 序列化 / 解析 ====================

def dump_result(model: BaseModel) -> str:
    """统一把 Pydantic 返回模型序列化为 JSON 字符串。"""
    return json.dumps(model.model_dump(), ensure_ascii=False, default=str)


def parse_tool_result(content: Any) -> Optional[dict]:
    """
    健壮地反序列化工具返回载荷。

    支持：
    - str：json.loads 解析，要求结果是 dict
    - dict：直接返回
    - list：内容块形式（如 [{"type":"text","text": "{...}"}]），提取 text 再解析

    任何无法解析的情况返回 None（统一兜底，不再在调用处散落 try/except）。
    """
    if content is None:
        return None

    if isinstance(content, dict):
        return content

    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and "text" in block:
                return parse_tool_result(block.get("text"))
            # 块本身可能就是载荷
            parsed = parse_tool_result(block)
            if parsed is not None:
                return parsed
        return None

    if isinstance(content, str):
        try:
            obj = json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return obj if isinstance(obj, dict) else None

    return None


__all__ = [
    "QueryResult", "ChartResult",
    "StatisticalSummaryResult", "DataProfileResult", "ExportResult",
    "RESULT_SCHEMAS", "RESULT_KEEP_FIELDS",
    "dump_result", "parse_tool_result",
]