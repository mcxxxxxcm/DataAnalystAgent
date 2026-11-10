"""
数据分析 Agent 创建器

支持短期记忆（多轮对话上下文保持）
使用 AsyncPostgresSaver 实现持久化存储
"""
from typing import Optional, Dict, Any, List
from functools import lru_cache
import asyncio
import threading

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    before_model, HumanInTheLoopMiddleware, SummarizationMiddleware,
)
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from config.settings import get_settings
from tools import get_enabled_tools
from middleware import (
    get_middleware_list,
    get_interrupt_on_config,
    get_checkpointer,
    get_async_checkpointer,
    get_store
)
from middleware.truncation import condense_tool_results
from .prompts import build_system_prompt


def _llm_cache_model_kwargs(system_prompt: str) -> Optional[Dict[str, Any]]:
    """提示词缓存（B005）：按 config 注入显式 cache 头。关闭/未配置 → None（不注入，零改动）。"""
    settings = get_settings()
    if not settings.prompt_cache_enabled or not settings.prompt_cache_header_json:
        return None
    from .prompt_cache import build_cache_kwargs
    header = build_cache_kwargs(system_prompt, settings.prompt_cache_header_json)
    return {"model_kwargs": {"extra_body": header}} if header else None


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
        # 并发冷启动去重：同名 name 在建的 asyncio.Task，避免多个协程重复 create_async_agent
        self._async_agent_pending: Dict[Any, asyncio.Task] = {}
        # 同步版并发保护（多线程调用 create_agent 时互斥）
        self._sync_lock = threading.Lock()
        self.max_tokens = 4000

    def create_agent(
            self,
            name: str = "data-analyst",
            custom_system_prompt: Optional[str] = None,
            custom_tools: Optional[List] = None,
            tool_scope: Optional[str] = None,
            enable_hitl: bool = True,
            enable_logging: bool = True,
            checkpointer: Optional[Any] = None
    ) -> Any:
        """
        创建数据分析 Agent（同步版本，使用内存 checkpointer）

        参数：
            name: Agent名称
            custom_system_prompt: 自定义系统提示词
            custom_tools: 自定义工具列表（优先于 tool_scope）
            tool_scope: 工具范围 full/read_only/query_only（未传时取配置 default_tool_scope）
            enable_hitl: 是否启用Human-in-the-Loop
            enable_logging: 是否启用日志
            checkpointer: 自定义checkpointer

        返回：
            配置好的 Agent 实例
        """
        system_prompt = custom_system_prompt or build_system_prompt(
            db_info=f"数据库: {self.settings.db_name}",
            custom_instructions="请用中文回复用户"
        )

        _extra_model = _llm_cache_model_kwargs(system_prompt) or {}
        llm = ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            **_extra_model,
        )

        tools = custom_tools or get_enabled_tools(tool_scope or self.settings.default_tool_scope)

        middleware = get_middleware_list(enable_logging=enable_logging)

        # 压缩工具返回载荷（降 token）
        @before_model
        def condense_tool_results_middleware(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
            messages = state.get("messages", [])
            condensed = condense_tool_results(messages)
            if condensed != messages:
                return {
                    "messages": [
                        RemoveMessage(id=REMOVE_ALL_MESSAGES),
                        *condensed
                    ]
                }
            return None

        middleware.append(condense_tool_results_middleware)

        # 长上下文自动摘要（官方中间件）：超过预算阈值时把早前历史摘要成一条
        # SystemMessage，保留最近 keep 条消息。较手写 trim 更不易剪坏 tool/human 配对。
        middleware.append(
            SummarizationMiddleware(
                model=llm,
                trigger=("tokens", self.settings.context_budget),
                token_counter=llm.get_num_tokens_from_messages,
            )
        )

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
            store=get_store(),
            middleware=middleware,
        )

        return agent

    async def create_async_agent(
            self,
            name: str = "data-analyst",
            custom_system_prompt: Optional[str] = None,
            custom_tools: Optional[List] = None,
            tool_scope: Optional[str] = None,
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
            custom_tools: 自定义工具列表（优先于 tool_scope）
            tool_scope: 工具范围 full/read_only/query_only（未传时取配置 default_tool_scope）
            enable_hitl: 是否启用Human-in-the-Loop
            enable_logging: 是否启用日志
            checkpointer: 自定义checkpointer

        返回：
            配置好的 Agent 实例
        """
        system_prompt = custom_system_prompt or build_system_prompt(
            db_info=f"数据库: {self.settings.db_name}",
            custom_instructions="请用中文回复用户"
        )

        _extra_model = _llm_cache_model_kwargs(system_prompt) or {}
        llm = ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            **_extra_model,
        )

        tools = custom_tools or get_enabled_tools(tool_scope or self.settings.default_tool_scope)

        middleware = get_middleware_list(enable_logging=enable_logging)

        # 工具返回载荷压缩（跨轮压缩 ToolMessage 载荷，降单条 token）
        @before_model
        async def condense_tool_results_middleware(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
            messages = state.get("messages", [])
            condensed = condense_tool_results(messages)
            if condensed != messages:
                return {
                    "messages": [
                        RemoveMessage(id=REMOVE_ALL_MESSAGES),
                        *condensed
                    ]
                }
            return None

        middleware.append(condense_tool_results_middleware)

        # 长上下文自动摘要（官方中间件）：预算超过 settings.context_budget 触发，
        # 用真实 model tokenizer 计数，保留最近 keep 条消息，早前历史摘要为 SystemMessage。
        middleware.append(
            SummarizationMiddleware(
                model=llm,
                trigger=("tokens", self.settings.context_budget),
                token_counter=llm.get_num_tokens_from_messages,
            )
        )

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
            store=get_store(),
            middleware=middleware,
        )

        return agent

    def get_cached_agent(self, name: str = "default") -> Any:
        """获取缓存的Agent实例（同步版本）"""
        with self._sync_lock:
            if name not in self._agent_cache:
                self._agent_cache[name] = self.create_agent()
        # 锁内构建完成后返回，不在锁内 return 避免不必要的锁持有
        return self._agent_cache[name]

    async def get_cached_async_agent(self, name: str = "default", tool_scope: Optional[str] = None) -> Any:
        """
        获取缓存的Agent实例（异步版本）

        使用 AsyncPostgresSaver，支持短期记忆。
        并发冷启动去重：同一缓存键在建的任务共享同一个 asyncio.Task，避免高并发首请求重复创建。
        - name：缓存键（默认 "default"，向后兼容）。
        - tool_scope：RBAC 角色可注入其权限子集；指定时按 scope 独立缓存。
        """
        if tool_scope:
            cache_key = f"scope:{tool_scope}"
            agent_name = f"data-analyst-{tool_scope}"
        else:
            cache_key = name
            agent_name = name
        if cache_key in self._async_agent_cache:
            return self._async_agent_cache[cache_key]
        if cache_key in self._async_agent_pending:
            return await self._async_agent_pending[cache_key]
        task = asyncio.create_task(self.create_async_agent(name=agent_name, tool_scope=tool_scope))
        self._async_agent_pending[cache_key] = task
        try:
            agent = await task
        except BaseException:
            self._async_agent_pending.pop(cache_key, None)
            raise
        self._async_agent_cache[cache_key] = agent
        self._async_agent_pending.pop(cache_key, None)
        return agent

    def clear_cache(self) -> None:
        """清除缓存"""
        self._agent_cache.clear()
        self._async_agent_cache.clear()
        self._async_agent_pending.clear()


agent_factory = AnalystAgentFactory()


def get_agent() -> Any:
    """
    获取默认Agent实例（同步版本）

    使用缓存，避免重复创建
    注意：使用内存 checkpointer，重启后记忆丢失
    """
    return agent_factory.get_cached_agent()


async def get_async_agent(tool_scope: Optional[str] = None) -> Any:
    """
    获取Agent实例（异步版本,持久化短期记忆）。

    可指定 tool_scope（RBAC 角色注入其权限子集用）；None 用配置 default_tool_scope。
    """
    return await agent_factory.get_cached_async_agent(tool_scope=tool_scope)


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
