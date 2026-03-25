"""
数据库基础设施模块

提供数据库连接和Schema管理能力
这些是内部基础设施，不暴露给LLM
"""

from .pool import db_pool, DatabasePool, PoolStats
from .schema import schema_manager, SchemaManager, TableSchema, ColumnInfo, ForeignKeyInfo

__all__ = [
    "db_pool",
    "DatabasePool",
    "PoolStats",
    "schema_manager",
    "SchemaManager",
    "TableSchema",
    "ColumnInfo",
    "ForeignKeyInfo"
]