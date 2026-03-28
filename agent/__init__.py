"""
Agent 模块

提供数据分析 Agent 的创建和运行能力
支持短期记忆（多轮对话上下文保持）
"""

from .prompts import (
    SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    format_system_prompt,
    format_few_shot_examples
)

__all__ = [
    "SYSTEM_PROMPT",
    "FEW_SHOT_EXAMPLES",
    "format_system_prompt",
    "format_few_shot_examples",

    "AnalystAgentFactory",
    "agent_factory",
    "get_agent",
    "get_async_agent",
    "run_query",
    "handle_interrupt"
]


def __getattr__(name):
    """延迟导入 agent 相关模块"""
    if name in ("AnalystAgentFactory", "agent_factory", "get_agent", "get_async_agent", "run_query", "handle_interrupt"):
        from .analyst_agent import (
            AnalystAgentFactory,
            agent_factory,
            get_agent,
            get_async_agent,
            run_query,
            handle_interrupt
        )
        globals()["AnalystAgentFactory"] = AnalystAgentFactory
        globals()["agent_factory"] = agent_factory
        globals()["get_agent"] = get_agent
        globals()["get_async_agent"] = get_async_agent
        globals()["run_query"] = run_query
        globals()["handle_interrupt"] = handle_interrupt
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")