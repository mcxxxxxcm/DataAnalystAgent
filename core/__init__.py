"""
Core 基础设施层

包含所有不暴露给LLM的基础设施代码：
- database: 数据库连接和Schema
- security: 安全校验、清理、风险评估

说明：重依赖（asyncpg、langchain 等）均延迟导入，
既能降低启动开销，也便于对安全等纯逻辑模块进行单元测试。
"""

__all__ = [
    # Database (延迟导入)
    "db_pool",
    "schema_manager",

    # Security (延迟导入)
    "sql_validator",
    "sql_sanitizer",
    "risk_assessor",
    "SQLRiskLevel"
]


def __getattr__(name):
    """延迟导入 database / security 模块"""
    if name in ("db_pool", "schema_manager"):
        from .database import db_pool, schema_manager
        globals()["db_pool"] = db_pool
        globals()["schema_manager"] = schema_manager
        return locals()[name]
    if name in ("sql_validator", "sql_sanitizer", "risk_assessor", "SQLRiskLevel"):
        from .security import sql_validator, sql_sanitizer, risk_assessor, SQLRiskLevel
        globals()[name] = locals()[name]
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")