"""
中间件配置模块（更新版）

位置：middleware/config.py
职责：配置官方中间件 + 本地日志 + 短期记忆

使用 AsyncPostgresSaver 实现持久化的短期记忆
支持多轮对话上下文保持
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

    if enable_logging:
        middlewares.append(logging_middleware)

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

    for tool in hitl_config.tools_requiring_approval:
        allowed = hitl_config.allowed_decisions.get(tool, {'approve', 'reject'})
        interrupt_on[tool] = {
            "allowed_decisions": list(allowed)
        }

    for tool in hitl_config.auto_approve_tools:
        interrupt_on[tool] = False

    return interrupt_on


_async_checkpointer_instance = None
_checkpointer_context_manager = None


def get_checkpointer():
    """
    获取同步 checkpointer（用于兼容旧代码）

    使用内存 checkpointer（开发环境）
    生产环境应使用 get_async_checkpointer
    """
    return InMemorySaver()


async def get_async_checkpointer():
    """
    获取异步 checkpointer

    优先使用已初始化的 AsyncPostgresSaver（持久化短期记忆）
    如果未初始化则使用 InMemorySaver（内存短期记忆）

    两者都支持多轮对话上下文保持，区别在于：
    - InMemorySaver: 重启后记忆丢失
    - AsyncPostgresSaver: 记忆持久化到数据库

    返回:
        checkpointer 实例
    """
    global _async_checkpointer_instance

    if _async_checkpointer_instance is not None:
        return _async_checkpointer_instance

    _async_checkpointer_instance = InMemorySaver()
    return _async_checkpointer_instance


async def setup_checkpointer():
    """
    初始化 checkpointer 数据库表

    在应用启动时调用，创建所需的数据库表
    并初始化全局 checkpointer 实例
    """
    global _async_checkpointer_instance, _checkpointer_context_manager

    try:
        from config.settings import get_settings
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        settings = get_settings()

        db_uri = (
            f"postgresql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
        )
        
        print(f"[Checkpointer] Connecting to PostgreSQL: {settings.db_host}:{settings.db_port}/{settings.db_name}")

        _checkpointer_context_manager = AsyncPostgresSaver.from_conn_string(db_uri)
        checkpointer = await _checkpointer_context_manager.__aenter__()
        
        print("[Checkpointer] Creating checkpoint tables...")
        await checkpointer.setup()
        
        _async_checkpointer_instance = checkpointer
        print("[Checkpointer] ✅ PostgreSQL checkpointer initialized successfully!")
        print("[Checkpointer] Short-term memory will persist across restarts.")

    except Exception as e:
        print(f"[Checkpointer] ❌ PostgreSQL setup failed: {type(e).__name__}: {e}")
        print("[Checkpointer] Falling back to InMemorySaver (memory lost on restart)")
        _async_checkpointer_instance = InMemorySaver()


async def close_checkpointer():
    """
    关闭 checkpointer 连接

    在应用关闭时调用
    """
    global _checkpointer_context_manager

    if _checkpointer_context_manager is not None:
        try:
            await _checkpointer_context_manager.__aexit__(None, None, None)
        except Exception:
            pass
        _checkpointer_context_manager = None


def reset_checkpointer():
    """重置 checkpointer 实例（用于测试）"""
    global _async_checkpointer_instance, _checkpointer_context_manager
    _async_checkpointer_instance = None
    _checkpointer_context_manager = None


def get_dev_middleware_config():
    """开发环境配置"""
    return {
        "middleware": get_middleware_list(enable_logging=True),
        "interrupt_on": get_interrupt_on_config(),
        "checkpointer": get_checkpointer()
    }