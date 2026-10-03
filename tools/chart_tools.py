"""
智能图表生成工具

默认路径：声明式 ECharts option（token 极少、前端矢量渲染、精度更高）。
- create_chart 按 result_id 从结果缓存取数，服务端构建 option，返回 option_id 句柄。
进阶路径：create_custom_chart 让 LLM 写 matplotlib 代码（风险高，默认关闭）。
"""

from langchain_core.tools import tool
from typing import List, Dict, Any, Optional
import asyncio
import time

from utils.result_store import get_result
from utils.chart_spec import build_echarts_option
from utils.chart_sandbox import execute_chart_code
from tools.result_schemas import ChartResult, dump_result

from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chart_")


# 全局缓存，用于存储生成的 ECharts option（带 TTL 与上限，防止无界增长）
_spec_cache: Dict[str, Dict[str, Any]] = {}
_spec_expiry: Dict[str, float] = {}
_SPEC_TTL_SECONDS = 600  # 10 分钟过期
_SPEC_MAX_ENTRIES = 50


def _store_spec(chart_id: str, option: Dict[str, Any]) -> None:
    """存储图表 spec，超上限时淘汰最早的条目"""
    now = time.time()
    _spec_cache[chart_id] = option
    _spec_expiry[chart_id] = now + _SPEC_TTL_SECONDS

    if len(_spec_cache) > _SPEC_MAX_ENTRIES:
        oldest_id = min(_spec_expiry, key=_spec_expiry.get)
        _spec_cache.pop(oldest_id, None)
        _spec_expiry.pop(oldest_id, None)


def get_cached_spec(chart_id: str) -> Optional[Dict[str, Any]]:
    """从缓存获取图表 option（过期自动失效并移除）"""
    expiry = _spec_expiry.get(chart_id)
    if expiry is None:
        return None
    if time.time() > expiry:
        _spec_cache.pop(chart_id, None)
        _spec_expiry.pop(chart_id, None)
        return None
    return _spec_cache.pop(chart_id, None)


@tool
async def create_chart(
    result_id: str,
    chart_type: Optional[str] = None,
    x_field: Optional[str] = None,
    y_field: Optional[str] = None,
    title: str = ""
) -> str:
    """
    创建图表（推荐使用，声明式 ECharts option，token 极少）。

    数据取自 result_id（query_database 返回的 result_id），无需再次传数据。
    服务端按数据特征自动校验字段并构建图表；chart_type 省略时自动推荐。

    参数:
        result_id: query_database 返回的结果引用ID
        chart_type: 可选 - bar(柱状图), line(折线图), pie(饼图), scatter(散点图)
        x_field: X轴字段（饼图为标签字段）
        y_field: Y轴字段（饼图为数值字段）
        title: 图表标题

    返回:
        JSON结果，包含 option_id（前端经 /api/chart/option/<id> 获取ECharts option渲染）
    """
    spec = get_result(result_id)
    if spec is None:
        result = ChartResult(success=False, error="result_id 不存在或已过期，请先执行 query_database 获取有效的 result_id")
        return dump_result(result)

    built = build_echarts_option(
        chart_type=chart_type,
        columns=spec["columns"],
        rows=spec["rows"],
        x_field=x_field,
        y_field=y_field,
        title=title,
    )

    if not built["success"]:
        return dump_result(ChartResult(success=False, error=built["error"]))

    chart_id = uuid()
    _store_spec(chart_id, built["option"])

    return dump_result(ChartResult(
        success=True,
        chart_type=built["chart_type"],
        option_id=f"chart_id:{chart_id}",
        message=f"{built['chart_type']}图表已生成",
    ))


def uuid() -> str:
    import uuid as _uuid
    return str(_uuid.uuid4())[:8]


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
        return dump_result(result)

    if len(data) > 100:
        data = data[:100]

    loop = asyncio.get_event_loop()

    def _create_custom_chart():
        return execute_chart_code(code, data)

    try:
        result_dict = await loop.run_in_executor(_executor, _create_custom_chart)

        if result_dict["success"]:
            chart_id = uuid()
            _store_spec(chart_id, {"_png_base64": result_dict["image_base64"]})

            result = ChartResult(
                success=True,
                chart_type="custom",
                option_id=f"chart_id:{chart_id}",
                message="自定义图表已生成"
            )
        else:
            result = ChartResult(
                success=False,
                error=result_dict["error"]
            )

        return dump_result(result)

    except Exception as e:
        result = ChartResult(success=False, error=str(e))
        return dump_result(result)


def warmup_matplotlib():
    """预热 matplotlib，建议在启动时调用（从原 viz_tools 迁移而来）"""
    try:
        from utils.chart_sandbox import get_safe_globals
        get_safe_globals([])
        print("Matplotlib 预热完成")
    except Exception as e:
        print(f"Matplotlib 预热失败: {e}")


CHART_TOOLS = [create_chart]