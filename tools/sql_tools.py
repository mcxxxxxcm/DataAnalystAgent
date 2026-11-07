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
import re

from core.database import db_pool, schema_manager
from config.settings import get_settings
from tools.result_schemas import QueryResult, dump_result
from tools.boundaries import guard_query_sql, is_allowed_table
from core.security.sql_error import build_self_correction_message, is_transient_error
from utils.result_store import set_result
from utils.effect_queue import run_sql_durable, sql_key

# SELECT 类查询返回上限，建议 LLM 用 LIMIT 缩小范围，超出部分截断
_SELECT_HARD_CAP = get_settings().sql_max_rows


def _is_write_dml(sql: str) -> str:
    """识别写操作 DML 类型（INSERT/UPDATE/DELETE）；非写操作返回空串。"""
    head = str(sql).lstrip().upper()
    for kw in ('INSERT', 'UPDATE', 'DELETE'):
        if head.startswith(kw):
            return kw
    return ""


def _parse_affected_rows(tag: str) -> int:
    """解析 asyncpg execute 返回的 tag（形如 'INSERT 0 1' / 'DELETE 3'）末尾的受影响行数。"""
    parts = str(tag).split()
    if parts:
        try:
            return int(parts[-1])
        except (TypeError, ValueError):
            return 0
    return 0


def _has_returning(sql: str) -> bool:
    """是否带 RETURNING 子句（写后回看写入行）。"""
    return bool(re.search(r"\bRETURNING\b", str(sql or ""), re.IGNORECASE))


def _build_write_result(write_type: str, payload, *, execution_time: float = 0.0) -> QueryResult:
    """构建写操作结果：
    - payload 为行列表（RETURNING）→ 回显 data/columns，result_id 留空（写结果不入 result_store）；
    - payload 为受影响行数整数（无 RETURNING）→ 返回 {操作, 受影响行数}。
    """
    if not isinstance(payload, (list, tuple)):
        affected = int(payload)
        return QueryResult(
            success=True, row_count=affected,
            data=[{"操作": write_type, "受影响行数": affected}],
            columns=["操作", "受影响行数"], execution_time=execution_time,
        )
    rows = [dict(r) for r in payload]
    columns = list(rows[0].keys()) if rows else []
    return QueryResult(
        success=True, data=rows, row_count=len(rows), columns=columns,
        execution_time=execution_time,
    )


@tool
async def query_database(query: str) -> str:
    """执行 SQL。
    参数: query - SQL 语句。
    说明: 语句将先经安全校验（SELECT 默认放行；写操作需 enable_sql_write=True；
    禁止 DROP/TRUNCATE/ALTER/CREATE 及危险函数/注入）。SELECT 自动附加 LIMIT 防止全表扫描；
    写操作（INSERT/UPDATE/DELETE）需 enable_sql_write=True，UPDATE/DELETE 必须带 WHERE 限定范围；
    写后默认返回受影响行数；写语句建议加 RETURNING（如 INSERT ... RETURNING id）以回看写入后的真实数据；
    批量插入用多行 VALUES (...), (...)，即单条 INSERT 一次插入多行。
    """
    start_time = time.time()
    timeout = get_settings().sql_timeout
    try:
        sql, error = await guard_query_sql(query)
        if error:
            result = QueryResult(success=False, error=error, execution_time=time.time() - start_time)
            return dump_result(result)

        write_type = _is_write_dml(sql)
        _cfg_retries = get_settings().effect_queue_max_retries
        _cfg_delay = get_settings().effect_queue_base_delay
        _sql_key = sql_key(sql)

        if write_type:
            # 写操作：执行 + 写后失效 schema 缓存（刷新 stale 的 row_count/sample_data）；
            # 结果不入 result_store（写结果不适合作图表数据源，避免越界）。
            schema_manager.clear_cache()
            if _has_returning(sql):
                # RETURNING：用 fetch 抓回写入后的真实行回显给用户（不存引用缓存）
                rows = await run_sql_durable(
                    db_pool.fetch, key=_sql_key, max_retries=_cfg_retries,
                    base_delay=_cfg_delay, args=(sql,), kwargs={"timeout": timeout},
                )
                result = _build_write_result(write_type, rows, execution_time=time.time() - start_time)
            else:
                tag = await run_sql_durable(
                    db_pool.execute, key=_sql_key, max_retries=_cfg_retries,
                    base_delay=_cfg_delay, args=(sql,), kwargs={"timeout": timeout},
                )
                affected = _parse_affected_rows(tag)
                result = _build_write_result(write_type, affected, execution_time=time.time() - start_time)
            return dump_result(result)

        rows = await run_sql_durable(
            db_pool.fetch, key=_sql_key, max_retries=_cfg_retries,
            base_delay=_cfg_delay, args=(sql,), kwargs={"timeout": timeout},
        )
        data = [dict(row) for row in rows]
        columns = list(rows[0].keys()) if rows else []
        # 结果入引用缓存，供 create_chart 按 result_id 取数，避免 LLM 重传完整数据
        result_id = set_result(columns, data) if rows else ""
        result = QueryResult(
            success=True, data=data[: _SELECT_HARD_CAP], row_count=len(data),
            columns=columns, result_id=result_id, execution_time=time.time() - start_time
        )
        return dump_result(result)
    except Exception as e:
        # 瞬时/可恢复错误（连接中断、死锁、超时等）直接抛出，交给 ToolRetryMiddleware 原样重试；
        # 逻辑错误（列/表名错、语法错、除零等）才转结构化失败回喂 LLM 走自纠。
        if is_transient_error(e):
            raise
        result = QueryResult(success=False, error=build_self_correction_message(str(e), exc=e),
                             execution_time=time.time() - start_time)
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