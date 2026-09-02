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
import json
import time

from core.database import db_pool, schema_manager
from config.settings import get_settings
from tools.result_schemas import QueryResult, dump_result
from tools.boundaries import guard_query_sql, is_allowed_table

# SELECT 类查询返回上限，建议 LLM 用 LIMIT 缩小范围，超出部分截断
_SELECT_HARD_CAP = get_settings().sql_max_rows


@tool
async def query_database(query: str) -> str:
    """执行 SQL 查询。
    参数: query - SQL 语句。
    说明: 语句将先经安全校验（仅允许 SELECT，写操作需 enable_sql_write=True；
    禁止 DROP/TRUNCATE/ALTER/CREATE 及危险函数/注入），并自动附加 LIMIT 防止全表扫描。
    """
    start_time = time.time()
    timeout = get_settings().sql_timeout
    try:
        sql, error = await guard_query_sql(query)
        if error:
            result = QueryResult(success=False, error=error, execution_time=time.time() - start_time)
            return dump_result(result)

        rows = await db_pool.fetch(sql, timeout=timeout)
        data = [dict(row) for row in rows]
        columns = list(rows[0].keys()) if rows else []
        result = QueryResult(
            success=True, data=data[: _SELECT_HARD_CAP], row_count=len(data),
            columns=columns, execution_time=time.time() - start_time
        )
        return dump_result(result)
    except Exception as e:
        result = QueryResult(success=False, error=str(e), execution_time=time.time() - start_time)
        return dump_result(result)


@tool
async def list_tables() -> str:
    """列出数据库中所有表名"""
    tables = await schema_manager.list_tables()
    return json.dumps({"tables": tables}, ensure_ascii=False)


@tool
async def get_table_schema(table_name: str) -> str:
    """获取表结构。参数: table_name - 表名"""
    table = await is_allowed_table(table_name)
    schema = await schema_manager.get_table_schema(table)
    return schema.to_llm_format()


@tool
async def get_sample_data(table_name: str, limit: int = 3) -> str:
    """获取表样本数据。参数: table_name - 表名, limit - 行数"""
    table = await is_allowed_table(table_name)
    clamp = max(1, min(int(limit), _SELECT_HARD_CAP))
    data = await schema_manager.get_sample_data(table, clamp)
    return json.dumps({"table": table, "sample_data": data}, ensure_ascii=False, default=str)


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