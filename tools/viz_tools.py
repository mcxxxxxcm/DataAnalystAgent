"""
可视化工具 - 优化版

位置：tools/viz_tools.py
职责：提供数据可视化能力

优化措施：
1. 延迟导入 matplotlib，避免启动时加载
2. 简化字体配置，避免字体搜索
3. 降低图片尺寸和 dpi
4. 使用线程池异步执行
"""

from langchain_core.tools import tool
from typing import List, Dict, Any
from pydantic import BaseModel
import json
import base64
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 延迟导入的全局变量
_plt = None
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chart_")


class ChartResult(BaseModel):
    """图表结果"""
    success: bool
    chart_type: str = ""
    image_base64: str = ""
    message: str = ""
    error: str = ""


def _get_plt():
    """延迟获取 matplotlib.pyplot，避免启动时加载"""
    global _plt
    if _plt is None:
        import matplotlib
        matplotlib.use('Agg')  # 必须在导入 pyplot 之前
        import matplotlib.pyplot as plt
        _plt = plt
        
        # 配置中文字体支持
        # Windows 系统常见中文字体优先级
        chinese_fonts = [
            'Microsoft YaHei',      # 微软雅黑
            'SimHei',               # 黑体
            'SimSun',               # 宋体
            'KaiTi',                # 楷体
            'FangSong',             # 仿宋
            'Arial Unicode MS',     # Mac
            'DejaVu Sans',          # Linux fallback
        ]
        
        # 查找可用的中文字体
        from matplotlib.font_manager import FontManager
        fm = FontManager()
        available_fonts = [f.name for f in fm.ttflist]
        
        font_found = None
        for font in chinese_fonts:
            if font in available_fonts:
                font_found = font
                break
        
        if font_found:
            plt.rcParams['font.sans-serif'] = [font_found]
        else:
            # 如果没有找到中文字体，使用系统默认
            plt.rcParams['font.sans-serif'] = ['sans-serif']
        
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        
        if font_found:
            print(f"Matplotlib 使用字体: {font_found}")
        else:
            print("警告: 未找到中文字体，图表中文可能显示为方框")
    
    return _plt


def _create_line_chart_sync(
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str,
    x_label: str,
    y_label: str
) -> str:
    """同步创建折线图"""
    try:
        plt = _get_plt()
        
        x_values = [str(d[x_field]) for d in data]
        y_values = [float(d[y_field]) for d in data]

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(x_values, y_values, marker='o', linewidth=2, markersize=5)
        ax.set_title(title, fontsize=12)
        ax.set_xlabel(x_label or x_field, fontsize=10)
        ax.set_ylabel(y_label or y_field, fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=80)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close(fig)

        result = ChartResult(
            success=True,
            chart_type="line",
            image_base64=image_base64,
            message=f"折线图已生成，共{len(data)}个数据点"
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)

    except Exception as e:
        result = ChartResult(success=False, error=str(e))
        return json.dumps(result.model_dump(), ensure_ascii=False)


def _create_bar_chart_sync(
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str,
    x_label: str,
    y_label: str
) -> str:
    """同步创建柱状图"""
    try:
        plt = _get_plt()
        
        x_values = [str(d[x_field]) for d in data]
        y_values = [float(d[y_field]) for d in data]

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(x_values, y_values, color='steelblue', alpha=0.8)
        ax.set_title(title, fontsize=12)
        ax.set_xlabel(x_label or x_field, fontsize=10)
        ax.set_ylabel(y_label or y_field, fontsize=10)
        ax.grid(True, alpha=0.3, axis='y')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=80)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close(fig)

        result = ChartResult(
            success=True,
            chart_type="bar",
            image_base64=image_base64,
            message=f"柱状图已生成，共{len(data)}个数据点"
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)

    except Exception as e:
        result = ChartResult(success=False, error=str(e))
        return json.dumps(result.model_dump(), ensure_ascii=False)


def _create_pie_chart_sync(
    data: List[Dict[str, Any]],
    label_field: str,
    value_field: str,
    title: str
) -> str:
    """同步创建饼图"""
    try:
        plt = _get_plt()
        
        labels = [str(d[label_field]) for d in data]
        values = [float(d[value_field]) for d in data]

        fig, ax = plt.subplots(figsize=(7, 7))
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
        ax.set_title(title, fontsize=12)
        plt.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=80)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close(fig)

        result = ChartResult(
            success=True,
            chart_type="pie",
            image_base64=image_base64,
            message="饼图已生成"
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)

    except Exception as e:
        result = ChartResult(success=False, error=str(e))
        return json.dumps(result.model_dump(), ensure_ascii=False)


@tool
async def create_line_chart(
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "折线图"
) -> str:
    """创建折线图。参数: data-数据列表, x_field-X轴字段, y_field-Y轴字段, title-标题"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        _create_line_chart_sync,
        data, x_field, y_field, title, "", ""
    )
    return result


@tool
async def create_bar_chart(
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "柱状图"
) -> str:
    """创建柱状图。参数: data-数据列表, x_field-X轴字段, y_field-Y轴字段, title-标题"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        _create_bar_chart_sync,
        data, x_field, y_field, title, "", ""
    )
    return result


@tool
async def create_pie_chart(
    data: List[Dict[str, Any]],
    label_field: str,
    value_field: str,
    title: str = "饼图"
) -> str:
    """创建饼图。参数: data-数据列表, label_field-标签字段, value_field-数值字段, title-标题"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        _create_pie_chart_sync,
        data, label_field, value_field, title
    )
    return result


def warmup_matplotlib():
    """预热 matplotlib，建议在启动时调用"""
    try:
        plt = _get_plt()
        # 创建一个空白图表预热
        fig, ax = plt.subplots()
        plt.close(fig)
        print("Matplotlib 预热完成")
    except Exception as e:
        print(f"Matplotlib 预热失败: {e}")


# 导出所有可视化工具
VIZ_TOOLS = [
    create_line_chart,
    create_bar_chart,
    create_pie_chart
]
