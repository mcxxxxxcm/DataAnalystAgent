"""
查询结果缓存

有界 + TTL 的结果缓存，用于把 query_database 的查询结果以 result_id 引用化，
图表工具按 id 取数，避免 LLM 把完整结果重新序列化进工具参数（token 优化）。
"""

import time
import uuid
from typing import Any, Dict, List, Optional

# 有界缓存，带过期时间与容量上限，防止无界增长
_store: Dict[str, Dict[str, Any]] = {}
_expiry: Dict[str, float] = {}
_TTL_SECONDS = 600  # 10 分钟过期
_MAX_ENTRIES = 50


def set_result(columns: List[str], rows: List[Dict[str, Any]]) -> str:
    """存储一次查询结果，返回 result_id"""
    result_id = uuid.uuid4().hex[:12]
    now = time.time()
    _store[result_id] = {"columns": columns, "rows": rows}
    _expiry[result_id] = now + _TTL_SECONDS

    if len(_store) > _MAX_ENTRIES:
        oldest_id = min(_expiry, key=_expiry.get)
        _store.pop(oldest_id, None)
        _expiry.pop(oldest_id, None)

    return result_id


def get_result(result_id: str) -> Optional[Dict[str, Any]]:
    """按 id 取结果；过期自动失效并移除。返回 {columns, rows} 或 None"""
    expiry = _expiry.get(result_id)
    if expiry is None:
        return None
    if time.time() > expiry:
        _store.pop(result_id, None)
        _expiry.pop(result_id, None)
        return None
    return _store.get(result_id)


def clear() -> None:
    """清空缓存（测试用）"""
    _store.clear()
    _expiry.clear()