"""
单一写者纪律断言：读不写。

迁移 dsh-superagent core 的「one writer per state」「Read queries never write」。
断言本项目各内存缓存的**读路径不摧毁条目**（别名：读后条目仍在、读不改变 size）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.bounded_cache import BoundedTTLCache
import tools.chart_tools as chart_tools
import utils.result_store as result_store


def test_chart_spec_read_is_non_destructive():
    """get_cached_spec 读后条目仍在（不再是被删除的 .pop()）。"""
    cap = _reset_and_use_raw_cache()
    chart_tools._store_spec("k1", {"x": 1})
    assert chart_tools.get_cached_spec("k1") == {"x": 1}
    assert cap.get("k1") == {"x": 1}  # 读后仍在
    assert cap.size() == 1


def test_chart_spec_multiple_reads_same_value():
    cap = _reset_and_use_raw_cache()
    chart_tools._store_spec("k2", {"x": 2})
    assert chart_tools.get_cached_spec("k2") == {"x": 2}
    assert chart_tools.get_cached_spec("k2") == {"x": 2}  # 重读/重试仍可取到


def test_result_store_read_is_non_destructive():
    result_store.clear()
    rid = result_store.set_result(["a"], [{"a": 1}])
    assert result_store.get_result(rid) is not None
    assert result_store.get_result(rid) is not None  # 读后条目仍在
    assert result_store.cache_size() == 1


def test_result_store_get_after_set_preserves_entry():
    result_store.clear()
    rid = result_store.set_result(["a"], [{"a": 1}])
    first = result_store.get_result(rid)
    result_store.clear()
    assert first is not None


def _reset_and_use_raw_cache() -> BoundedTTLCache:
    """把图表 spec 缓存换成全新的 BoundedTTLCache 以便直接操作/断言。"""
    cap = BoundedTTLCache()
    chart_tools._spec_cache = cap
    return cap