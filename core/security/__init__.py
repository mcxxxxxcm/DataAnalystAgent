"""
安全基础设施模块

提供SQL安全相关的所有功能：
- 校验：检查SQL是否安全
- 清理：清理和转换SQL
- 风险评估：评估操作风险等级

这些是内部基础设施，不暴露给LLM
"""

from .sql_validator import (
    SQLValidator,
    SQLRiskLevel,
    SQLErrorType,
    ValidationResult,
    create_validator
)

from .sql_sanitizer import (
    SQLSanitizer,
    SanitizationResult,
    create_sanitizer
)

from .risk_assessor import (
    RiskAssessor,
    RiskAssessment,
    RiskFactor
)

__all__ = [
    # 校验器
    "SQLValidator",
    "SQLRiskLevel",
    "SQLErrorType",
    "ValidationResult",
    "sql_validator",
    "create_validator",

    # 清理器
    "SQLSanitizer",
    "SanitizationResult",
    "sql_sanitizer",
    "create_sanitizer",

    # 风险评估
    "RiskAssessor",
    "RiskAssessment",
    "RiskFactor",
    "risk_assessor"
]


def __getattr__(name):
    """延迟创建实例"""
    if name == "sql_validator":
        from .sql_validator import sql_validator as sv
        globals()["sql_validator"] = sv
        return sv
    elif name == "sql_sanitizer":
        from .sql_sanitizer import sql_sanitizer as ss
        globals()["sql_sanitizer"] = ss
        return ss
    elif name == "risk_assessor":
        from .risk_assessor import risk_assessor as ra
        globals()["risk_assessor"] = ra
        return ra
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")