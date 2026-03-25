"""
中间件配置模块（更新版）

位置：middleware/config.py
职责：配置官方中间件 + 本地日志

不使用 LangSmith，所有日志存储在本地
"""

from typing import Dict, Set, Optional, List
from dataclasses import dataclass, field

from langgraph.checkpoint.memory import InMemorySaver

from .logging_wrapper import logging_middleware


@dataclass
class HITLConfig:
    """Human-in-the-Loop 配置"""

    tools_requiring_approval: Set[str] = field(default_factory=lambda: {
        'query_database',
    })

    allowed_decisions: Dict[str, Set[str]] = field(default_factory=lambda: {
        'query_database': {'approve', 'reject'},
    })

    auto_approve_tools: Set[str] = field(default_factory=lambda: {
        'list_tables',
        'get_table_schema',
        'get_sample_data',
        'get_relevant_schemas',
    })


def get_middleware_list(
        hitl_config: Optional[HITLConfig] = None,
        enable_logging: bool = True
) -> List:
    """
    获取中间件列表

    返回用于 create_deep_agent 的 middleware 参数

    参数:
        hitl_config: HITL配置
        enable_logging: 是否启用日志

    返回:
        中间件列表
    """
    middlewares = []

    # 1. 日志中间件（本地）
    if enable_logging:
        middlewares.append(logging_middleware)

    # 注意：HumanInTheLoopMiddleware 通过 interrupt_on 参数配置
    # 不是通过 middleware 列表

    return middlewares


def get_interrupt_on_config(
        hitl_config: Optional[HITLConfig] = None
) -> Dict:
    """
    获取 interrupt_on 配置

    用于 create_deep_agent 的 interrupt_on 参数

    参数:
        hitl_config: HITL配置

    返回:
        interrupt_on 配置字典
    """
    hitl_config = hitl_config or HITLConfig()

    interrupt_on = {}

    # 需要审核的工具
    for tool in hitl_config.tools_requiring_approval:
        allowed = hitl_config.allowed_decisions.get(tool, {'approve', 'reject'})
        interrupt_on[tool] = {
            "allowed_decisions": list(allowed)
        }

    # 自动批准的工具
    for tool in hitl_config.auto_approve_tools:
        interrupt_on[tool] = False

    return interrupt_on


def get_checkpointer():
    """
    获取 checkpointer

    使用内存 checkpointer（开发环境）
    生产环境可替换为 PostgresSaver
    """
    return InMemorySaver()


# 预设配置
def get_dev_middleware_config():
    """开发环境配置"""
    return {
        "middleware": get_middleware_list(enable_logging=True),
        "interrupt_on": get_interrupt_on_config(),
        "checkpointer": get_checkpointer()
    }