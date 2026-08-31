"""
数据分析工具

位置：tools/analysis_tools.py
职责：为 LLM 提供描述统计、数据质量探查与结果导出能力

设计：
- 表名校验：通过 schema_manager.list_tables() 白名单，表名无法参数化，必须防注入
- 阻塞型 pandas 计算放到 ThreadPoolExecutor，避免阻塞事件循环
- export_result 复用 core/security 的 SQL 校验/清理（只读 + 自动 LIMIT）
"""

import asyncio
import time
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from langchain_core.tools import tool

from core.database import db_pool, schema_manager
from config.settings import get_settings
from utils.export_manager import export_manager
from tools.result_schemas import (
    StatisticalSummaryResult, DataProfileResult, ExportResult, dump_result,
)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis_")

# 合法标识符：字母/数字/下划线，防止表名列名注入
_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_]+$')


async def _resolve_table(table_name: str) -> str:
    """
    校验表名在白名单内并返回规范化表名。

    抛 ValueError 表示表不存在或表名非法。
    """
    if not table_name or not _IDENTIFIER_RE.match(table_name):
        raise ValueError(f"非法表名: {table_name!r}")
    tables = await schema_manager.list_tables()
    if table_name not in tables:
        raise ValueError(f"表不存在: {table_name}，可用表: {sorted(tables)}")
    return table_name


async def _fetch_table(table_name: str) -> pd.DataFrame:
    """读取表数据（按采样上限），返回 DataFrame"""
    settings = get_settings()
    cap = min(settings.sql_max_rows, settings.export_max_rows)
    rows = await db_pool.fetch(f"SELECT * FROM {table_name} LIMIT {cap}")
    return pd.DataFrame([dict(r) for r in rows])


def _serialize(value):
    """将 numpy 标量/NaN 转为 JSON 可序列化值"""
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


@tool
async def statistical_summary(table_name: str, columns: list = None) -> str:
    """
    获取表各列的统计摘要（推荐用于理解数据分布，大大节省反复查询）。

    数值列返回 count/mean/std/min/25%/50%/75%/max；
    非数值列返回 count/unique/top/freq。

    参数:
        table_name: 表名
        columns: 可选，要统计的列名列表；默认统计全表
    """
    start = time.time()
    try:
        table = await _resolve_table(table_name)
        df = await _fetch_table(table)
        if df.empty:
            return dump_result(StatisticalSummaryResult(
                success=True, table=table, row_count_sampled=0, note="表为空"
            ))

        cols = columns if columns else list(df.columns)
        cols = [c for c in cols if c in df.columns]

        def _compute():
            stats = {}
            for col in cols:
                series = df[col]
                if pd.api.types.is_numeric_dtype(series):
                    desc = series.describe()
                    stats[col] = {
                        "type": "numeric",
                        "count": _serialize(desc.get("count")),
                        "mean": _serialize(desc.get("mean")),
                        "std": _serialize(desc.get("std")),
                        "min": _serialize(desc.get("min")),
                        "q25": _serialize(desc.get("25%")),
                        "median": _serialize(desc.get("50%")),
                        "q75": _serialize(desc.get("75%")),
                        "max": _serialize(desc.get("max")),
                        "missing": int(series.isna().sum()),
                    }
                else:
                    vc = series.value_counts(dropna=True)
                    top = vc.head(1)
                    stats[col] = {
                        "type": "categorical",
                        "count": _serialize(series.count()),
                        "unique": int(series.nunique(dropna=True)),
                        "top": str(top.index[0]) if len(top) else None,
                        "freq": _serialize(top.iloc[0]) if len(top) else None,
                        "missing": int(series.isna().sum()),
                    }
            return stats

        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(_executor, _compute)
        return dump_result(StatisticalSummaryResult(
            success=True,
            table=table,
            row_count_sampled=len(df),
            columns=stats,
            execution_time=round(time.time() - start, 3),
        ))
    except Exception as e:
        return dump_result(StatisticalSummaryResult(success=False, error=str(e)))


@tool
async def data_profile(table_name: str) -> str:
    """
    数据质量探查：返回表的行数、重复率，以及每列的缺失率/唯一值比例/类型/长度范围。

    参数:
        table_name: 表名
    """
    start = time.time()
    try:
        table = await _resolve_table(table_name)
        df = await _fetch_table(table)
        if df.empty:
            return dump_result(DataProfileResult(
                success=True, table=table, row_count=0, duplicate_ratio=0.0,
            ))

        def _build():
            total = len(df)
            dup_ratio = round(float(df.duplicated().mean()), 4)
            profile = {}
            for col in df.columns:
                series = df[col]
                non_null = int(series.notna().sum())
                missing = total - non_null
                unique = int(series.nunique(dropna=True))
                if pd.api.types.is_numeric_dtype(series):
                    col_type = "numeric"
                    min_len = max_len = None
                else:
                    col_type = "categorical"
                    lens = series.dropna().astype(str).str.len()
                    min_len = _serialize(lens.min()) if len(lens) else None
                    max_len = _serialize(lens.max()) if len(lens) else None
                profile[col] = {
                    "type": col_type,
                    "non_null": non_null,
                    "missing": missing,
                    "missing_ratio": round(missing / total, 4) if total else 0.0,
                    "unique": unique,
                    "unique_ratio": round(unique / total, 4) if total else 0.0,
                    "str_len_min": min_len,
                    "str_len_max": max_len,
                }
            return total, dup_ratio, profile

        loop = asyncio.get_event_loop()
        total, dup_ratio, profile = await loop.run_in_executor(_executor, _build)
        return dump_result(DataProfileResult(
            success=True,
            table=table,
            row_count=total,
            duplicate_ratio=dup_ratio,
            columns=profile,
            execution_time=round(time.time() - start, 3),
        ))
    except Exception as e:
        return dump_result(DataProfileResult(success=False, error=str(e)))


@tool
async def export_result(query: str, file_format: str = "csv", filename: str = None) -> str:
    """
    执行查询并把结果导出为本地文件（CSV 或 xlsx），返回下载地址。

    参数:
        query: SQL 查询语句（只允许 SELECT）
        file_format: 导出格式 - csv 或 xlsx
        filename: 可选，文件名前缀（不传则自动生成）
    """
    start = time.time()
    try:
        if file_format not in ("csv", "xlsx"):
            return dump_result(ExportResult(success=False, error="file_format 仅支持 csv 或 xlsx"))

        from core.security import sql_validator, sql_sanitizer

        validation = sql_validator.validate(query)
        if not validation.is_valid:
            return dump_result(ExportResult(
                success=False, error=f"SQL 校验失败: {validation.error_message}"
            ))

        sanitized = sql_sanitizer.sanitize(query)
        final_sql = sanitized.sanitized_sql

        rows = await db_pool.fetch(final_sql, timeout=get_settings().sql_timeout)
        df = pd.DataFrame([dict(r) for r in rows])

        export_file = export_manager.save_dataframe(df, file_format, filename)
        return dump_result(ExportResult(
            success=True,
            file_id=export_file.file_id,
            filename=export_file.filename,
            row_count=len(df),
            download_url=f"/api/export/{export_file.file_id}",
            execution_time=round(time.time() - start, 3),
        ))
    except Exception as e:
        return dump_result(ExportResult(success=False, error=str(e)))


ANALYSIS_TOOLS = [
    statistical_summary,
    data_profile,
    export_result,
]