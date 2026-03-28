"""
SQL查询工具

位置：tools/sql_tools.py
职责：定义LLM可调用的SQL相关工具

注意：
- 这里只定义工具接口
- 安全校验由 middleware/ 自动处理
- 底层实现由 core/ 提供
"""

from langchain_core.tools import tool
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import json
import time

from core.database import db_pool, schema_manager


class QueryResult(BaseModel):
    """查询结果"""
    success: bool
    data: List[Dict[str, Any]] = []
    row_count: int = 0
    columns: List[str] = []
    error: str = ""
    execution_time: float = 0.0


@tool
async def query_database(query: str) -> str:
    """执行 SQL 查询。参数: query - SQL 语句（SELECT/INSERT/UPDATE/DELETE）"""
    start_time = time.time()
    try:
        rows = await db_pool.fetch(query, timeout=30)
        data = [dict(row) for row in rows]
        columns = list(rows[0].keys()) if rows else []
        result = QueryResult(
            success=True, data=data, row_count=len(data),
            columns=columns, execution_time=time.time() - start_time
        )
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
    except Exception as e:
        result = QueryResult(success=False, error=str(e), execution_time=time.time() - start_time)
        return json.dumps(result.model_dump(), ensure_ascii=False)


@tool
async def list_tables() -> str:
    """列出数据库中所有表名"""
    tables = await schema_manager.list_tables()
    return json.dumps({"tables": tables}, ensure_ascii=False)


@tool
async def get_table_schema(table_name: str) -> str:
    """获取表结构。参数: table_name - 表名"""
    schema = await schema_manager.get_table_schema(table_name)
    return schema.to_llm_format()


@tool
async def get_sample_data(table_name: str, limit: int = 3) -> str:
    """获取表样本数据。参数: table_name - 表名, limit - 行数"""
    data = await schema_manager.get_sample_data(table_name, limit)
    return json.dumps({"table": table_name, "sample_data": data}, ensure_ascii=False, default=str)


@tool
async def get_relevant_schemas(query: str) -> str:
    """获取相关表结构。参数: query - 用户查询"""
    schemas = await schema_manager.get_relevant_schemas(query)
    return schemas


# 导出所有工具
SQL_TOOLS = [
    query_database,
    list_tables,
    get_table_schema,
    get_sample_data,
    get_relevant_schemas
]