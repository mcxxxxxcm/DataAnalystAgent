"""
长期记忆工具（PostgresStore）

位置：tools/memory_tools.py
职责：让 Agent 能显式记住/召回跨会话的语义事实（用户偏好、数据口径、常用过滤约定等），
并预留成功 NL→SQL 对照的沉淀入口。

实现：
- remember(key, value)：写入 PostgresStore，namespace=("memory", category)
- recall(key)：读取该 namespace 内的记忆
- 底层 get_store() 全局实例在 middleware/config 初始化（AsyncPostgresStore）

注意：
- tools 是无状态函数，拿不到 thread_id 上下文，故用 category 命名空间隔离。
- PostgresStore 未初始化时（如未建表）静默降级，不抛错影响主流程。
"""

from langchain_core.tools import tool


def _get_store():
    """惰性取全局 PostgresStore（避免模块导入期耦合 middleware）。"""
    from middleware.config import get_store
    return get_store()


@tool
async def remember(key: str, value: str, category: str = "custom") -> str:
    """记住一条跨会话事实。
    参数: key - 记忆键(如 '客户口径')；value - 记忆内容(如 'VIP客户指年消费>1万的客户')；
    category - 分类命名空间(默认 custom)。"""
    try:
        store = _get_store()
        if store is None:
            return "记忆存储未启用（未初始化 PostgresStore），本次未保存"
        await store.aput(("memory", category), key, {"value": value})
        return f"已记住 [{category}/{key}]"
    except Exception as e:
        return f"记忆保存失败: {e}"


@tool
async def recall(key: str, category: str = "custom") -> str:
    """召回一条跨会话记住的事实。参数: key - 记忆键；category - 与 remember 一致的分类。"""
    try:
        store = _get_store()
        if store is None:
            return "记忆存储未启用（未初始化 PostgresStore）"
        item = await store.aget(("memory", category), key)
        if item is None:
            return f"未找到记忆 [{category}/{key}]"
        return str(item.value.get("value", ""))
    except Exception as e:
        return f"记忆召回失败: {e}"


def save_nl_sql_pair(nl: str, sql: str, category: str = "nl2sql"):
    """
    沉淀一条成功执行的 NL→SQL 对照（预留扩展）。

    需要调用方同时持有 NL 与 SQL；当前 query_database 拿不到 NL(在 human message)，
    故预留此入口，后续可在具备 thread 上下文的中间件处接入。
    """
    return remember.ainvoke({"key": f"nl:{nl[:40]}", "value": sql, "category": category})


MEMORY_TOOLS = [remember, recall]


__all__ = ["remember", "recall", "save_nl_sql_pair", "MEMORY_TOOLS"]