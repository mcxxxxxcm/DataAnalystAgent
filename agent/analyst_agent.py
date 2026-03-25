"""
数据分析 Agent 创建器
"""
from typing import Optional, Dict, Any, List
from functools import lru_cache
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from deepagents import create_deep_agent

from config.settings import get_settings
from tools import SQL_TOOLS
from middleware import (
    get_middleware_list,
    get_interrupt_on_config,
    get_checkpointer
)
from .prompts import format_system_prompt


class AnalystAgentFactory:
    """
    数据分析Agent工厂
    负责创建和配置Deep Agent实例
    """

    def __init__(self):
        self.settings = get_settings()
        self._agent_cache: Dict[Any, Any] = {}

    def create_agent(
            self,
            name: str = "data-analyst",
            custom_system_prompt: Optional[str] = None,
            custom_tools: Optional[List] = None,
            enable_hitl: bool = True,
            enable_logging: bool = True,
            checkpointer: Optional[Any] = None
    ) -> Any:
        """
        创建数据分析 Agent
        参数：
            name: Agent名称
            custom_system_prompt: 自定义系统提示词
            custom_tools: 自定义工具列表
            enable_hitl: 是否启用Human-in-the-Loop
            enable_logging: 是否启用日志
            checkpointer: 自定义checkpointer
        返回：
            配置好的 Agent 实例
        """
        # 创建LLM
        llm = ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.api_key,
            base_url=self.settings.base_url
        )

        # 系统提示词
        system_prompt = custom_system_prompt or format_system_prompt(
            db_info=f"数据库: {self.settings.db_name}",
            custom_instructions="请用中文回复用户"
        )

        # 工具列表
        tools = custom_tools or SQL_TOOLS

        # 中间件
        middleware = get_middleware_list(enable_logging=enable_logging)

        # HITL配置
        interrupt_on = get_interrupt_on_config() if enable_hitl else {}

        # Checkpointer
        cp = checkpointer or get_checkpointer()

        # 创建Agent
        agent = create_deep_agent(
            name=name,
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
            # middleware=middleware,
            interrupt_on=interrupt_on,
            checkpointer=cp
        )

        return agent

    def get_cached_agent(self, name: str = "default") -> Any:
        """获取缓存的Agent实例"""
        if name not in self._agent_cache:
            self._agent_cache[name] = self.create_agent()
        return self._agent_cache[name]

    def clear_cache(self) -> None:
        """清除缓存"""
        self._agent_cache.clear()


# 全局工厂实例
agent_factory = AnalystAgentFactory()


def get_agent() -> Any:
    """
    获取默认Agent实例

    使用缓存，避免重复创建
    """
    return agent_factory.get_cached_agent()


async def run_query(
        query: str,
        thread_id: str,
        agent: Optional[Any] = None
) -> Dict[str, Any]:
    """
    执行查询的便捷函数

    参数:
        query: 用户查询
        thread_id: 会话ID
        agent: Agent实例（可选）

    返回:
        查询结果
    """
    from langgraph.types import Command

    agent = agent or get_agent()

    config = {"configurable": {"thread_id": thread_id}}

    # 执行查询
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]},
        config=config
    )

    return result


async def handle_interrupt(
        thread_id: str,
        decision: str,
        message: Optional[str] = None,
        agent: Optional[Any] = None
) -> Dict[str, Any]:
    """
    处理中断（Human-in-the-Loop审核）

    参数:
        thread_id: 会话ID
        decision: 决策类型
        message: 拒绝原因（reject时使用）
        agent: Agent实例

    返回:
        继续执行的结果
    """
    from langgraph.types import Command

    agent = agent or get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    # 构建决策
    decision_data = {"type": decision}
    if message:
        decision_data["message"] = message

    # 恢复执行
    result = await agent.ainvoke(
        Command(resume={"decisions": [decision_data]}),
        config=config
    )

    return result
