"""
数据分析 Agent 创建器

支持短期记忆（多轮对话上下文保持）
使用 AsyncPostgresSaver 实现持久化存储
"""
from typing import Optional, Dict, Any, List
from functools import lru_cache

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import before_model, HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from config.settings import get_settings
from tools import ALL_TOOLS
from middleware import (
    get_middleware_list,
    get_interrupt_on_config,
    get_checkpointer,
    get_async_checkpointer
)
from .prompts import format_system_prompt


class AnalystAgentFactory:
    """
    数据分析Agent工厂
    负责创建和配置Deep Agent实例
    支持短期记忆（多轮对话上下文保持）
    """

    def __init__(self):
        self.settings = get_settings()
        self._agent_cache: Dict[Any, Any] = {}
        self._async_agent_cache: Dict[Any, Any] = {}
        self.max_tokens = 4000

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
        创建数据分析 Agent（同步版本，使用内存 checkpointer）

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
        llm = ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.api_key,
            base_url=self.settings.base_url
        )

        system_prompt = custom_system_prompt or format_system_prompt(
            db_info=f"数据库: {self.settings.db_name}",
            custom_instructions="请用中文回复用户"
        )

        tools = custom_tools or ALL_TOOLS

        middleware = get_middleware_list(enable_logging=enable_logging)

        if enable_hitl:
            interrupt_on = get_interrupt_on_config()
            middleware.append(
                HumanInTheLoopMiddleware(interrupt_on=interrupt_on)
            )

        cp = checkpointer or get_checkpointer()

        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=cp,
            middleware=middleware,
        )

        return agent

    async def create_async_agent(
            self,
            name: str = "data-analyst",
            custom_system_prompt: Optional[str] = None,
            custom_tools: Optional[List] = None,
            enable_hitl: bool = True,
            enable_logging: bool = True,
            checkpointer: Optional[Any] = None
    ) -> Any:
        """
        创建数据分析 Agent（异步版本，使用 AsyncPostgresSaver）

        使用 AsyncPostgresSaver 实现持久化的短期记忆
        支持多轮对话上下文保持

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
        llm = ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.api_key,
            base_url=self.settings.base_url
        )

        system_prompt = custom_system_prompt or format_system_prompt(
            db_info=f"数据库: {self.settings.db_name}",
            custom_instructions="请用中文回复用户"
        )

        tools = custom_tools or ALL_TOOLS

        middleware = get_middleware_list(enable_logging=enable_logging)

        # 添加消息裁剪中间件
        @before_model
        async def trim_messages_middleware(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
            """裁剪消息历史，保持在 max_tokens 限制内"""
            messages = state.get("messages", [])
            
            print(f"[trim_messages] 当前消息数量: {len(messages)}")
            
            if len(messages) <= 3:
                print(f"[trim_messages] 消息数量 <= 3，跳过裁剪")
                return None
            
            before_tokens = count_tokens_approximately(messages)
            print(f"[trim_messages] 裁剪前 token 数: {before_tokens}")
            
            trimmed = trim_messages(
                messages,
                strategy="last",
                token_counter=count_tokens_approximately,
                max_tokens=self.max_tokens,
                start_on="human",
                end_on=("human", "tool"),
            )
            
            after_tokens = count_tokens_approximately(trimmed)
            print(f"[trim_messages] 裁剪后 token 数: {after_tokens}, 消息数: {len(trimmed)}")
            
            return {
                "messages": [
                    RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    *trimmed
                ]
            }

        middleware.append(trim_messages_middleware)

        if enable_hitl:
            interrupt_on = get_interrupt_on_config()
            middleware.append(
                HumanInTheLoopMiddleware(interrupt_on=interrupt_on)
            )

        cp = checkpointer or await get_async_checkpointer()

        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=cp,
            middleware=middleware,
        )

        return agent

    def get_cached_agent(self, name: str = "default") -> Any:
        """获取缓存的Agent实例（同步版本）"""
        if name not in self._agent_cache:
            self._agent_cache[name] = self.create_agent()
        return self._agent_cache[name]

    async def get_cached_async_agent(self, name: str = "default") -> Any:
        """
        获取缓存的Agent实例（异步版本）

        使用 AsyncPostgresSaver，支持短期记忆
        """
        if name not in self._async_agent_cache:
            self._async_agent_cache[name] = await self.create_async_agent()
        return self._async_agent_cache[name]

    def clear_cache(self) -> None:
        """清除缓存"""
        self._agent_cache.clear()
        self._async_agent_cache.clear()


agent_factory = AnalystAgentFactory()


def get_agent() -> Any:
    """
    获取默认Agent实例（同步版本）

    使用缓存，避免重复创建
    注意：使用内存 checkpointer，重启后记忆丢失
    """
    return agent_factory.get_cached_agent()


async def get_async_agent() -> Any:
    """
    获取默认Agent实例（异步版本）

    使用 AsyncPostgresSaver，支持持久化的短期记忆
    多轮对话上下文会保存在数据库中
    """
    return await agent_factory.get_cached_async_agent()


async def run_query(
        query: str,
        thread_id: str,
        agent: Optional[Any] = None
) -> Dict[str, Any]:
    """
    执行查询的便捷函数

    参数:
        query: 用户查询
        thread_id: 会话ID（用于短期记忆，相同 thread_id 保持上下文）
        agent: Agent实例（可选）

    返回:
        查询结果
    """
    from langgraph.types import Command

    agent = agent or await get_async_agent()

    config = {"configurable": {"thread_id": thread_id}}

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

    agent = agent or await get_async_agent()
    config = {"configurable": {"thread_id": thread_id}}

    decision_data = {"type": decision}
    if message:
        decision_data["message"] = message

    result = await agent.ainvoke(
        Command(resume={"decisions": [decision_data]}),
        config=config
    )

    return result
