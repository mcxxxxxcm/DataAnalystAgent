"""
声明式 ECharts option 构建

把查询结果（columns+rows）构建为紧凑的 ECharts option JSON，前端用 ECharts 矢量渲染。
相比让 LLM 写命令式绘图代码，spec-first 更小、更稳、更精确；字段缺失时给出精确错误，
驱动 LLM 用真实列名精准重试。
"""

from typing import Any, Dict, List, Optional

_CHART_TYPES = {"bar", "line", "pie", "scatter"}


def _is_numeric(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def recommend_chart_type(
    columns: List[str], rows: List[Dict[str, Any]], x_field: str, y_field: str
) -> str:
    """
    按 X 列基数与 Y 列数值性自动推荐图型：
    - X 列唯一值少（<=20）且 Y 为数值 → bar
    - 数值 X 且 Y 数值 → scatter
    - 数值 X 且有序（>=6 唯一值）→ line
    兜底 bar。
    """
    x_values = [row.get(x_field) for row in rows if row.get(x_field) is not None]
    y_values = [row.get(y_field) for row in rows if row.get(y_field) is not None]
    x_cardinality = len(set(x_values)) if x_values else 0
    y_is_numeric = all(_is_numeric(v) for v in y_values) if y_values else False
    x_is_numeric = all(_is_numeric(v) for v in x_values) if x_values else False

    if y_is_numeric:
        if x_is_numeric:
            if x_cardinality >= 6:
                return "line"
            return "scatter"
        if x_cardinality <= 20:
            return "bar"
    return "bar"


def _build_option(
    chart_type: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "",
) -> Dict[str, Any]:
    if chart_type == "pie":
        return _build_pie_option(columns, rows, x_field, y_field, title)
    return _build_xy_option(chart_type, columns, rows, x_field, y_field, title)


def _build_xy_option(
    chart_type: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "",
) -> Dict[str, Any]:
    # dataset.source：首行列头 + 数据行，配合 encode 声明 x/y 字段
    source = [list(columns)]
    for row in rows:
        source.append([row.get(c) for c in columns])

    option: Dict[str, Any] = {
        "title": {"text": title or f"{y_field} by {x_field}"},
        "tooltip": {"trigger": "axis"},
        "dataset": {"source": source},
        "xAxis": {"type": "category"},
        "yAxis": {"type": "value"},
        "series": [{
            "type": chart_type,
            "encode": {"x": x_field, "y": y_field},
        }],
    }
    return option


def _build_pie_option(
    columns: List[str],
    rows: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "",
) -> Dict[str, Any]:
    data = [{"name": row.get(x_field), "value": row.get(y_field)} for row in rows]
    option: Dict[str, Any] = {
        "title": {"text": title or f"{y_field} by {x_field}"},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "series": [{
            "type": "pie",
            "radius": "60%",
            "data": data,
            "label": {"show": True, "formatter": "{b}: {c}"},
        }],
    }
    return option


def build_echarts_option(
    chart_type: Optional[str],
    columns: List[str],
    rows: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "",
) -> Dict[str, Any]:
    """
    构建 ECharts option。

    返回:
        {"success": bool, "option": dict, "chart_type": str, "error": str}
        失败时 error 列出合法字段，便于 LLM 精准重试。
    """
    if not columns:
        return {"success": False, "option": {}, "chart_type": "", "error": "查询结果无列数据"}

    if x_field not in columns or y_field not in columns:
        valid = ", ".join(columns)
        return {
            "success": False,
            "option": {},
            "chart_type": "",
            "error": f"字段不存在：x_field={x_field!r}, y_field={y_field!r}。合法字段：{valid}",
        }

    if not rows:
        return {"success": False, "option": {}, "chart_type": "", "error": "查询结果为空，无法生成图表"}

    if chart_type is None:
        chart_type = recommend_chart_type(columns, rows, x_field, y_field)
    if chart_type not in _CHART_TYPES:
        return {
            "success": False,
            "option": {},
            "chart_type": "",
            "error": f"不支持的图表类型 {chart_type!r}，可选：{', '.join(sorted(_CHART_TYPES))}",
        }

    option = _build_option(chart_type, columns, rows, x_field, y_field, title)
    return {"success": True, "option": option, "chart_type": chart_type, "error": ""}