"""
RiskAssessor 写操作边界测试

锁定关键词：INSERT 不因"无 WHERE"被判危险写 DENY（插入新行本就不该有 WHERE）；
DELETE / UPDATE 无 WHERE 仍须判 CRITICAL→DENY；带 WHERE 的写操作判 HIGH→CONFIRM。
均为纯逻辑测试，不依赖真实数据库。
运行：pytest tests/test_risk_assessor.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")

from core.security.risk_assessor import RiskAssessor, Decision

assessor = RiskAssessor()


def test_insert_without_where_not_denied():
    """INSERT 无 WHERE 是合法语义，不应被 DENY（此前会把所有 INSERT 误杀）。"""
    a = assessor.assess("INSERT INTO sales (region, revenue) VALUES ('n', 100)")
    assert a.decision is not Decision.DENY
    assert a.risk_level.value != "critical"
    assert a.decision is Decision.CONFIRM  # 写操作仍需人工审核


def test_delete_without_where_still_denied():
    """DELETE 无 WHERE 会全表删除，必须判 CRITICAL→DENY 立即拒绝。"""
    a = assessor.assess("DELETE FROM sales")
    assert a.decision is Decision.DENY
    assert a.risk_level.value == "critical"


def test_update_without_where_still_denied():
    """UPDATE 无 WHERE 会改全表，必须判 CRITICAL→DENY。"""
    a = assessor.assess("UPDATE sales SET region = 'n'")
    assert a.decision is Decision.DENY
    assert a.risk_level.value == "critical"


def test_delete_with_where_confirms():
    """带 WHERE 的 DELETE 风险仍高，需人工审核(CONFIRM)，但不在守卫层直接拒绝。"""
    a = assessor.assess("DELETE FROM sales WHERE id = 3")
    assert a.decision is Decision.CONFIRM
    assert a.risk_level.value == "high"
    assert a.requires_approval


def test_update_with_where_confirms():
    a = assessor.assess("UPDATE sales SET region = 'n' WHERE id = 1")
    assert a.decision is Decision.CONFIRM
    assert a.risk_level.value == "high"


def test_insert_with_where_confirm():
    """带 WHERE 的 INSERT（少见但合法）同样走确认。"""
    a = assessor.assess("INSERT INTO sales (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    # WHERE 不在语句里，但 INSERT 语义不要求 WHERE；仍是写操作 → CONFIRM
    assert a.decision is Decision.CONFIRM
    assert a.risk_level.value == "high"


def test_safe_select_unchanged():
    a = assessor.assess("SELECT name FROM sales")
    assert a.decision is Decision.ALLOW
    assert a.risk_level.value == "safe"