"""
安全代码执行沙箱

用于安全执行 LLM 生成的绘图代码
"""

import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, Any, List, Optional


CHART_STYLES = {
    "colors": ["#4e79a7", "#f28e2c", "#e15759", "#76b7b2", "#59a14f", "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab"],
    "font_family": "SimHei",
    "figure_size": (8, 5),
    "dpi": 80
}


def get_safe_globals(data: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    获取安全的全局命名空间
    
    参数:
        data: 要传递给绘图代码的数据
    
    返回:
        安全的全局变量字典
    """
    safe_globals = {
        "__builtins__": {
            "list": list,
            "dict": dict,
            "str": str,
            "int": int,
            "float": float,
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "True": True,
            "False": False,
            "None": None,
        },
        "plt": plt,
        "np": np,
        "data": data or [],
        "CHART_STYLES": CHART_STYLES,
    }
    return safe_globals


def execute_chart_code(
    code: str,
    data: List[Dict[str, Any]],
    timeout: float = 10.0
) -> Dict[str, Any]:
    """
    安全执行绘图代码
    
    参数:
        code: Python 绘图代码
        data: 数据列表
        timeout: 执行超时时间（秒）
    
    返回:
        {"success": bool, "image_base64": str, "error": str}
    """
    try:
        plt.close('all')
        
        fig = plt.figure(figsize=CHART_STYLES["figure_size"], dpi=CHART_STYLES["dpi"])
        
        safe_globals = get_safe_globals(data)
        
        exec(code, safe_globals)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=CHART_STYLES["dpi"])
        plt.close('all')
        
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        
        return {
            "success": True,
            "image_base64": img_base64,
            "error": ""
        }
        
    except Exception as e:
        plt.close('all')
        return {
            "success": False,
            "image_base64": "",
            "error": str(e)
        }


def generate_chart_code_from_spec(
    chart_type: str,
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str = None,
    title: str = "",
    **kwargs
) -> str:
    """
    根据规格生成绘图代码
    
    参数:
        chart_type: 图表类型 (bar, line, pie, scatter)
        data: 数据列表
        x_field: X 轴字段
        y_field: Y 轴字段
        title: 图表标题
    
    返回:
        Python 绘图代码
    """
    if chart_type == "bar":
        code = f'''
x_data = [item['{x_field}'] for item in data]
y_data = [item['{y_field}'] for item in data]

plt.bar(x_data, y_data, color=CHART_STYLES['colors'][:len(x_data)])
plt.title('{title}', fontsize=14)
plt.xlabel('{x_field}', fontsize=12)
plt.ylabel('{y_field}', fontsize=12)
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
'''
    elif chart_type == "line":
        code = f'''
x_data = [item['{x_field}'] for item in data]
y_data = [item['{y_field}'] for item in data]

plt.plot(x_data, y_data, marker='o', color=CHART_STYLES['colors'][0], linewidth=2)
plt.title('{title}', fontsize=14)
plt.xlabel('{x_field}', fontsize=12)
plt.ylabel('{y_field}', fontsize=12)
plt.xticks(rotation=45, ha='right')
plt.grid(True, alpha=0.3)
plt.tight_layout()
'''
    elif chart_type == "pie":
        code = f'''
labels = [item['{x_field}'] for item in data]
values = [item['{y_field}'] for item in data]

plt.pie(values, labels=labels, autopct='%1.1f%%', colors=CHART_STYLES['colors'][:len(labels)])
plt.title('{title}', fontsize=14)
plt.tight_layout()
'''
    elif chart_type == "scatter":
        code = f'''
x_data = [item['{x_field}'] for item in data]
y_data = [item['{y_field}'] for item in data]

plt.scatter(x_data, y_data, c=CHART_STYLES['colors'][0], s=100, alpha=0.7)
plt.title('{title}', fontsize=14)
plt.xlabel('{x_field}', fontsize=12)
plt.ylabel('{y_field}', fontsize=12)
plt.grid(True, alpha=0.3)
plt.tight_layout()
'''
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")
    
    return code
