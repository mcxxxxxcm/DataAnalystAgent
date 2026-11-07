"""
写操作增强（RETURNING 回看 / 写入边界保持）纯逻辑测试。

覆盖 tools/sql_tools 的 _has_returning 与 _build_write_result；以及写未启用时 validator 仍拒绝（红线回归）。
不触真实 DB。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")

from tools.sql_tools import _has_returning, _build_write_result, _is_write_dml


def test_is_write_dml_detects_returning_insert():
    assert _is_write_dml("INSERT INTO sales (region, amount) VALUES ('n', 1) RETURNING id") == "INSERT"


def test_is_write_dml_case_insensitive():
    assert _is_write_dml("update users set vip_level=1 where id=2 returning id") == "UPDATE"


def test_has_returning_true():
    assert _has_returning("INSERT INTO t (a) VALUES (1) RETURNING id")


def test_has_returning_false():
    assert not _has_returning("INSERT INTO t (a) VALUES (1)")
    assert not _has_returning("SELECT * FROM t")  # SELECT 不误判


def test_build_write_result_returning_rows():
    rows = [{"id": 1, "region": "Jingdong"}, {"id": 2, "region": "Hangzhou"}]
    res = _build_write_result("INSERT", rows)
    assert res.success is True
    assert res.row_count == 2
    assert res.columns == ["id", "region"]
    assert res.data == rows
    # 写结果不入引用缓存：result_id 必须为空
    assert res.result_id == ""


def test_build_write_result_affected_count():
    res = _build_write_result("DELETE", 3)
    assert res.success is True
    assert res.row_count == 3
    assert res.data == [{"操作": "DELETE", "受影响行数": 3}]
    assert res.result_id == ""


def test_write_still_requires_enable_write():
    # 红线回归：enable_write=False 时写操作（含 RETURNING）仍被校验器拒绝
    from core.security.sql_validator import SQLValidator
    validator = SQLValidator(max_rows=100, enable_write=False, timeout=30)
    assert not validator.validate("INSERT INTO sales (region) VALUES ('n') RETURNING id").is_valid
    assert not validator.validate("DELETE FROM sales WHERE id=1 RETURNING id").is_valid


def test_update_without_where_still_denied():
    # 红线回归：DELETE/UPDATE 无 WHERE 仍被风险评估 DENY（不经 guard 放行）
    from core.security.risk_assessor import risk_assessor, Decision
    from core.security.sql_validator import SQLValidator
    validator = SQLValidator(max_rows=100, enable_write=True, timeout=30)
    # 校验层放行（写已启用），但风险评估必须 DENY 无 WHERE 更新
    assert validator.validate("DELETE FROM sales").is_valid
    assert risk_assessor.assess("DELETE FROM sales").decision == Decision.DENY