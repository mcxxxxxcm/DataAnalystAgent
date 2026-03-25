"""
Core 基础设施层

包含所有不暴露给LLM的基础设施代码：
- database: 数据库连接和Schema
- security: 安全校验、清理、风险评估
- execution: 代码执行环境（待实现）
"""

from .database import db_pool, schema_manager

__all__ = [
    # Database
    "db_pool",
    "schema_manager",

    # Security (延迟导入)
    "sql_validator",
    "sql_sanitizer",
    "risk_assessor",
    "SQLRiskLevel"
]


def __getattr__(name):
    """延迟导入 security 模块"""
    if name in ("sql_validator", "sql_sanitizer", "risk_assessor", "SQLRiskLevel"):
        from .security import sql_validator, sql_sanitizer, risk_assessor, SQLRiskLevel
        globals()[name] = locals()[name]
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")