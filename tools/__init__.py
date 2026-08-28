from .sql_tools import (
    query_database,
    list_tables,
    get_table_schema,
    get_sample_data,
    get_relevant_schemas,
    SQL_TOOLS
)
from .chart_tools import (
    create_chart,
    create_custom_chart,
    CHART_TOOLS
)
from config.settings import get_settings

# create_custom_chart 允许LLM生成并执行任意绘图代码，风险较高，
# 默认不对外暴露，可通过配置 enable_custom_chart=True 显式开启。
_settings = get_settings()
if _settings.enable_custom_chart:
    CHART_TOOLS = [create_chart, create_custom_chart]
else:
    CHART_TOOLS = [create_chart]

ALL_TOOLS = SQL_TOOLS + CHART_TOOLS

__all__ = [
    "query_database",
    "list_tables",
    "get_table_schema",
    "get_sample_data",
    "get_relevant_schemas",
    "SQL_TOOLS",
    "create_chart",
    "create_custom_chart",
    "CHART_TOOLS",
    "ALL_TOOLS"
]
