"""
core/security 模块单元测试

覆盖 SQLValidator / SQLSanitizer / RiskAssessor 的核心逻辑。
均为纯逻辑测试，不依赖真实数据库。
运行：pytest tests/test_security.py（在项目根目录执行）
"""
import os
import sys
import pytest

# 保证能导入项目模块，并提供测试可用的配置环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


@pytest.fixture
def validator():
    from core.security.sql_validator import SQLValidator
    # 直接实例化，避免依赖 .env 中的真实配置
    return SQLValidator(max_rows=100, enable_write=False, timeout=30)


@pytest.fixture
def validator_with_write():
    from core.security.sql_validator import SQLValidator
    return SQLValidator(max_rows=100, enable_write=True, timeout=30)


# -------------------- SQLValidator --------------------

def test_safe_select_passes(validator):
    result = validator.validate("SELECT name FROM sales")
    assert result.is_valid
    assert result.risk_level.value == "safe"


def test_drop_rejected(validator):
    result = validator.validate("DROP TABLE sales")
    assert not result.is_valid
    # DROP 可能在 AST 层被识别为 UNKNOWN(非DML) 或命中关键字黑名单，
    # 无论哪种路径都必须被拒绝。
    assert result.error_type.value in ("forbidden_operation", "forbidden_keyword")


def test_modifies_without_write_disabled(validator):
    result = validator.validate("DELETE FROM sales WHERE id = 1")
    assert not result.is_valid
    # 写操作未启用时，在 AST 层(DML不在白名单)即被拒绝
    assert result.error_type.value in ("forbidden_operation", "permission_denied")


def test_write_allowed_when_enabled(validator_with_write):
    result = validator_with_write.validate("DELETE FROM sales WHERE id = 1")
    assert result.is_valid
    assert result.risk_level.value == "high"


def test_empty_sql_rejected(validator):
    result = validator.validate("")
    assert not result.is_valid
    assert result.risk_level.value == "critical"


def test_forbidden_function_detected(validator):
    result = validator.validate("SELECT pg_read_file('/etc/passwd')")
    assert not result.is_valid
    assert result.error_type.value == "forbidden_function"


def test_multi_statement_injection(validator):
    result = validator.validate("SELECT * FROM sales; DROP TABLE orders")
    assert not result.is_valid


# -------------------- SQLSanitizer --------------------

@pytest.fixture
def sanitizer():
    from core.security.sql_sanitizer import SQLSanitizer
    return SQLSanitizer(max_rows=100, timeout=30)


def test_limit_injected_when_missing(sanitizer):
    result = sanitizer.sanitize("SELECT * FROM sales")
    assert result.limit_added
    assert "LIMIT 100" in result.sanitized_sql


def test_limit_not_added_when_present(sanitizer):
    result = sanitizer.sanitize("SELECT * FROM sales LIMIT 5")
    assert not result.limit_added


def test_dangerous_comment_removed(sanitizer):
    result = sanitizer.sanitize("SELECT * FROM sales -- DELETE FROM orders")
    assert result.comments_removed
    assert "-- DELETE FROM orders" not in result.sanitized_sql


def test_limit_not_injected_for_write(sanitizer):
    result = sanitizer.sanitize("UPDATE sales SET region='n' WHERE id=1")
    assert not result.limit_added


# -------------------- RiskAssessor --------------------

@pytest.fixture
def assessor():
    from core.security.risk_assessor import RiskAssessor
    return RiskAssessor()


def test_write_operation_requires_approval(assessor):
    assessment = assessor.assess("UPDATE sales SET region='n' WHERE id=1")
    assert assessment.requires_approval
    assert assessment.risk_level.value == "high"


def test_write_without_where_is_critical(assessor):
    assessment = assessor.assess("DELETE FROM sales")
    assert assessment.risk_level.value == "critical"
    assert assessment.requires_approval


def test_safe_select_auto_approved(assessor):
    assessment = assessor.assess("SELECT name FROM sales")
    assert not assessment.requires_approval
    assert assessment.risk_level.value == "safe"