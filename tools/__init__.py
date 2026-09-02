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
from .analysis_tools import (
    statistical_summary,
    data_profile,
    export_result,
    ANALYSIS_TOOLS
)
from config.settings import get_settings
import logging

# create_custom_chart 允许LLM生成并执行任意绘图代码，风险较高，
# 默认不对外暴露，可通过配置 enable_custom_chart=True 显式开启。
_settings = get_settings()
if _settings.enable_custom_chart:
    CHART_TOOLS = [create_chart, create_custom_chart]
else:
    CHART_TOOLS = [create_chart]

ALL_TOOLS = SQL_TOOLS + CHART_TOOLS + ANALYSIS_TOOLS

# 预定义只读分析子集：排除 export_result（写本地文件）与 create_custom_chart（任意代码执行）
_READ_ONLY_EXTRA = [statistical_summary, data_profile]

# 工具级权限子集。注入 agent 时按 scope 选择，实现读写/职责分层。
TOOL_SETS = {
    "full": ALL_TOOLS,
    "read_only": SQL_TOOLS + _READ_ONLY_EXTRA + CHART_TOOLS,
    "query_only": SQL_TOOLS,
}

_logger = logging.getLogger(__name__)


def get_enabled_tools(scope: str | None = None) -> list:
    """
    按 scope 返回允许的工具子集；未传则取配置 default_tool_scope。

    未知 scope 回退为 full 并记录告警，保证不因拼写错误缺失工具。
    """
    effective = scope or get_settings().default_tool_scope
    tools = TOOL_SETS.get(effective)
    if tools is None:
        _logger.warning("未知工具 scope=%r，回退为 full", effective)
        return TOOL_SETS["full"]
    return list(tools)

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
    "statistical_summary",
    "data_profile",
    "export_result",
    "ANALYSIS_TOOLS",
    "ALL_TOOLS",
    "TOOL_SETS",
    "get_enabled_tools"
]
