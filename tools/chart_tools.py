"""
智能图表生成工具

支持两种模式：
1. 简单模式：使用预定义模板（安全、快速）
2. 高级模式：LLM 生成代码执行（灵活）
"""

from langchain_core.tools import tool
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from utils.chart_sandbox import execute_chart_code, generate_chart_code_from_spec


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chart_")


class ChartResult(BaseModel):
    """图表结果"""
    success: bool
    chart_type: str = ""
    image_base64: str = ""
    message: str = ""
    error: str = ""


# 全局缓存，用于存储生成的图片
_chart_cache: Dict[str, str] = {}


def _truncate_base64(base64_str: str, max_length: int = 100) -> str:
    """截断 base64 字符串，避免消息过长"""
    if len(base64_str) <= max_length:
        return base64_str
    return base64_str[:max_length] + f"...[truncated, total {len(base64_str)} chars]"


@tool
async def create_chart(
    chart_type: Literal["bar", "line", "pie", "scatter"],
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = ""
) -> str:
    """
    创建图表（推荐使用）。
    
    参数:
        chart_type: 图表类型 - bar(柱状图), line(折线图), pie(饼图), scatter(散点图)
        data: 数据列表，如 [{"region": "华东", "revenue": 100}, ...]
        x_field: X轴字段名（饼图为标签字段）
        y_field: Y轴字段名（饼图为数值字段）
        title: 图表标题
    
    返回:
        JSON结果，包含图表 ID（图片存储在缓存中）
    """
    if not data:
        result = ChartResult(success=False, error="数据为空")
        return json.dumps(result.model_dump(), ensure_ascii=False)
    
    if len(data) > 100:
        data = data[:100]
    
    loop = asyncio.get_event_loop()
    
    def _create_chart():
        code = generate_chart_code_from_spec(
            chart_type=chart_type,
            data=data,
            x_field=x_field,
            y_field=y_field,
            title=title or f"{x_field} vs {y_field}"
        )
        return execute_chart_code(code, data)
    
    try:
        result_dict = await loop.run_in_executor(_executor, _create_chart)
        
        if result_dict["success"]:
            import uuid
            chart_id = str(uuid.uuid4())[:8]
            _chart_cache[chart_id] = result_dict["image_base64"]
            
            result = ChartResult(
                success=True,
                chart_type=chart_type,
                image_base64=f"chart_id:{chart_id}",
                message=f"{chart_type}图表已生成"
            )
        else:
            result = ChartResult(
                success=False,
                error=result_dict["error"]
            )
        
        return json.dumps(result.model_dump(), ensure_ascii=False)
        
    except Exception as e:
        result = ChartResult(success=False, error=str(e))
        return json.dumps(result.model_dump(), ensure_ascii=False)


@tool
async def create_custom_chart(
    code: str,
    data: List[Dict[str, Any]]
) -> str:
    """
    创建自定义图表（高级用户）。
    
    使用 Python matplotlib 代码自定义图表。
    可用变量: plt, np, data, CHART_STYLES
    
    参数:
        code: Python 绘图代码
        data: 数据列表
    
    示例代码:
        x = [item['region'] for item in data]
        y = [item['revenue'] for item in data]
        plt.bar(x, y, color=CHART_STYLES['colors'])
        plt.title('销售统计')
        plt.tight_layout()
    
    返回:
        JSON结果，包含图表 ID
    """
    if not code:
        result = ChartResult(success=False, error="代码为空")
        return json.dumps(result.model_dump(), ensure_ascii=False)
    
    if len(data) > 100:
        data = data[:100]
    
    loop = asyncio.get_event_loop()
    
    def _create_custom_chart():
        return execute_chart_code(code, data)
    
    try:
        result_dict = await loop.run_in_executor(_executor, _create_custom_chart)
        
        if result_dict["success"]:
            import uuid
            chart_id = str(uuid.uuid4())[:8]
            _chart_cache[chart_id] = result_dict["image_base64"]
            
            result = ChartResult(
                success=True,
                chart_type="custom",
                image_base64=f"chart_id:{chart_id}",
                message="自定义图表已生成"
            )
        else:
            result = ChartResult(
                success=False,
                error=result_dict["error"]
            )
        
        return json.dumps(result.model_dump(), ensure_ascii=False)
        
    except Exception as e:
        result = ChartResult(success=False, error=str(e))
        return json.dumps(result.model_dump(), ensure_ascii=False)


def get_cached_chart(chart_id: str) -> Optional[str]:
    """从缓存获取图表"""
    return _chart_cache.pop(chart_id, None)


CHART_TOOLS = [create_chart, create_custom_chart]
