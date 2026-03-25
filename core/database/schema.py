"""
数据库Schema管理

位置：core/database/schema.py
职责：获取和管理数据库结构信息，不暴露给LLM
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import asyncio

from core.database.pool import db_pool


@dataclass
class ColumnInfo:
    """列信息"""
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    default_value: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class ForeignKeyInfo:
    """外键信息"""
    column_name: str
    referenced_table: str
    referenced_column: str


@dataclass
class TableSchema:
    """表结构"""
    table_name: str
    columns: List[ColumnInfo]
    primary_keys: List[str]
    foreign_keys: List[ForeignKeyInfo]
    row_count: int
    comment: Optional[str] = None

    def to_llm_format(self) -> str:
        """转换为LLM友好格式"""
        lines = [f"表名: {self.table_name}"]

        if self.comment:
            lines.append(f"说明: {self.comment}")

        lines.append(f"约 {self.row_count:,} 行数据")
        lines.append("列:")

        for col in self.columns:
            pk_marker = " [主键]" if col.is_primary_key else ""
            nullable = "" if col.is_nullable else " [非空]"
            lines.append(f"  - {col.name}: {col.data_type}{pk_marker}{nullable}")

            if col.comment:
                lines.append(f"    注释: {col.comment}")

        if self.foreign_keys:
            lines.append("外键关系:")
            for fk in self.foreign_keys:
                lines.append(
                    f"  - {fk.column_name} -> {fk.referenced_table}.{fk.referenced_column}"
                )

        return "\n".join(lines)


class SchemaManager:
    """
    Schema管理器

    这是基础设施，不暴露给LLM
    提供 Schema 信息给 tools/ 使用
    """

    def __init__(self):
        self._cache: Dict[str, TableSchema] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = 3600

    async def list_tables(self) -> List[str]:
        """列出所有表名"""
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
        """
        rows = await db_pool.fetch(query)
        return [row['table_name'] for row in rows]

    async def get_table_schema(self, table_name: str) -> TableSchema:
        """获取表结构"""
        # 检查缓存
        if table_name in self._cache:
            cache_time = self._cache_time.get(table_name)
            if cache_time and (datetime.now() - cache_time).seconds < self._cache_ttl:
                return self._cache[table_name]

        # 并行查询
        columns_query = """
        SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
               COALESCE(col_description(t.oid, c.ordinal_position::int), '') as column_comment
        FROM information_schema.columns c
        JOIN pg_class t ON t.relname = c.table_name
        WHERE c.table_schema = 'public' AND c.table_name = $1
        ORDER BY c.ordinal_position;
        """

        pk_query = """
        SELECT a.attname as column_name
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        JOIN pg_class c ON c.oid = i.indrelid
        WHERE c.relname = $1 AND i.indisprimary;
        """

        fk_query = """
        SELECT kcu.column_name, ccu.table_name AS referenced_table, ccu.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = $1;
        """

        count_query = "SELECT reltuples::bigint as row_count FROM pg_class WHERE relname = $1;"

        columns_rows, pk_rows, fk_rows, count_row = await asyncio.gather(
            db_pool.fetch(columns_query, table_name),
            db_pool.fetch(pk_query, table_name),
            db_pool.fetch(fk_query, table_name),
            db_pool.fetchrow(count_query, table_name)
        )

        primary_keys = [row['column_name'] for row in pk_rows]

        columns = [
            ColumnInfo(
                name=row['column_name'],
                data_type=row['data_type'],
                is_nullable=row['is_nullable'] == 'YES',
                is_primary_key=row['column_name'] in primary_keys,
                default_value=row['column_default'],
                comment=row['column_comment'] if row['column_comment'] else None
            )
            for row in columns_rows
        ]

        foreign_keys = [
            ForeignKeyInfo(
                column_name=row['column_name'],
                referenced_table=row['referenced_table'],
                referenced_column=row['referenced_column']
            )
            for row in fk_rows
        ]

        schema = TableSchema(
            table_name=table_name,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            row_count=count_row['row_count'] if count_row else 0
        )

        self._cache[table_name] = schema
        self._cache_time[table_name] = datetime.now()

        return schema

    async def get_relevant_schemas(self, query: str, max_tables: int = 5) -> str:
        """获取相关表的Schema"""
        all_tables = await self.list_tables()
        query_lower = query.lower()

        relevant_tables = []
        for table in all_tables:
            if table.lower() in query_lower:
                relevant_tables.append(table)
            elif table.rstrip('s').lower() in query_lower:
                relevant_tables.append(table)

        if not relevant_tables:
            schemas_with_counts = []
            for table in all_tables[:10]:
                schema = await self.get_table_schema(table)
                schemas_with_counts.append((table, schema.row_count))
            schemas_with_counts.sort(key=lambda x: x[1], reverse=True)
            relevant_tables = [s[0] for s in schemas_with_counts[:max_tables]]

        schema_descriptions = []
        for table in relevant_tables[:max_tables]:
            schema = await self.get_table_schema(table)
            schema_descriptions.append(schema.to_llm_format())

        return "\n\n".join(schema_descriptions)

    async def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """获取样本数据"""
        query = f"SELECT * FROM {table_name} LIMIT {limit};"
        rows = await db_pool.fetch(query)
        return [dict(row) for row in rows]

    def clear_cache(self, table_name: Optional[str] = None) -> None:
        """清除缓存"""
        if table_name:
            self._cache.pop(table_name, None)
            self._cache_time.pop(table_name, None)
        else:
            self._cache.clear()
            self._cache_time.clear()


# 全局实例
schema_manager = SchemaManager()