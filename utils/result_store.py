"""
查询结果缓存

有界 + TTL 的结果缓存，用于把 query_database 的查询结果以 result_id 引用化，
图表工具按 id 取数，避免 LLM 把完整结果重新序列化进工具参数（token 优化）。
"""

import uuid
from typing import Any, Dict, List, Optional

from utils.cache_backend import CacheBackend, get_cache_backend

# 有界缓存，带过期时间与容量上限，防止无界增长。
# 单一写者：状态由 `_cache`（CacheBackend）独占写路径；本模块仅作薄委托，保持对外函数签名不变。
# TTL/容量单一来源在后端默认值（10 分钟过期 / 50 条），不在此另设配置（少设置审计）。
# 后端默认为进程内 memory；设 cache_backend=redis 后跨 worker 共享（backlog B006）。命名空间 rs: 防跨 owner 串写。
_cache: CacheBackend[str, Dict[str, Any]] = get_cache_backend(prefix="rs:")


def set_result(columns: List[str], rows: List[Dict[str, Any]]) -> str:
    """存储一次查询结果，返回 result_id"""
    result_id = uuid.uuid4().hex[:12]
    _cache.set(result_id, {"columns": columns, "rows": rows})
    return result_id


def get_result(result_id: str) -> Optional[Dict[str, Any]]:
    """按 id 取结果；过期自动失效并移除。返回 {columns, rows} 或 None（只读路径，非摧毁式）"""
    return _cache.get(result_id)


def clear() -> None:
    """清空缓存（测试用）"""
    _cache.clear()


def cache_size() -> int:
    """当前缓存条目数（可观测/压测用）"""
    return _cache.size()