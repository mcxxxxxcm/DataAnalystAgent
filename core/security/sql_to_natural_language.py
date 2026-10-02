"""
SQL → 自然语言回述

位置：core/security/sql_to_natural_language.py
职责：把待审 SQL 确定性翻译成一段中文业务描述，供 HITL 卡片与生成轨迹展示，
让用户「审业务语义」而非审裸 SQL（借鉴 Dataherald 的 SQL→NL、WrenAI 的 dry-plan）。

实现：纯正则、零额外 LLM 调用，解析结果确定可测。无法解析时回退原始 SQL 前缀。
"""

import re
from typing import Optional


def describe_sql(sql: str) -> str:
    """把 SQL 回述为中文业务描述。失败时返回原始语句前缀（带“原始SQL”标注）。"""
    if not sql or not str(sql).strip():
        return "（空 SQL）"

    text = re.sub(r"\s+", " ", str(sql)).strip()
    upper = text.upper()
    parts = []

    # 操作类型
    verb = "查询" if upper.startswith("SELECT") else (
        "插入" if upper.startswith("INSERT") else (
        "更新" if upper.startswith("UPDATE") else (
        "删除" if upper.startswith("DELETE") else "执行")))

    # 表名
    tables = _tables(text)
    parts.append(f"对 {('、'.join(tables) if tables else '目标表')} 表")

    # 筛选条件
    where = _between(text, "WHERE", ["GROUP BY", "HAVING", "ORDER BY", "LIMIT", "OFFSET"])
    if where:
        parts.append(f"按条件筛选({where})")

    # 分组
    groupby = _between(text, "GROUP BY", ["HAVING", "ORDER BY", "LIMIT", "OFFSET"])
    if groupby:
        parts.append(f"按 {groupby} 分组")

    # 聚合
    aggs = list(dict.fromkeys(m.group(0)[:30] for m in re.finditer(
        r"\b(SUM|COUNT|AVG|MIN|MAX|COALESCE)\s*\([^)]{0,40}\)", text, re.IGNORECASE)))
    if aggs:
        parts.append(f"计算 {'、'.join(aggs)}")
    elif verb == "查询":
        parts.append("读取数据")

    desc = f"{verb}：{'，'.join(parts)}。"

    limit = _between(text, "ORDER BY", ["LIMIT", "OFFSET"]) and _limit(text)
    if not limit:
        limit = _limit(text)
    desc += f"最多返回 {limit} 行。" if limit else "返回全部匹配结果（自动限制行数）。"

    return desc


def _compact(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _trunc(s: str, n: int = 50) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _tables(text: str) -> list:
    tables: list = []
    for kw in ("FROM", "JOIN", "INTO", "UPDATE", "DELETE FROM"):
        for m in re.finditer(r"\b" + re.escape(kw) + r"\s+([a-zA-Z_][a-zA-Z0-9_$]*)", text, re.IGNORECASE):
            tbl = m.group(1)
            if tbl and tbl.upper() not in [t.upper() for t in tables]:
                tables.append(tbl)
    return tables


def _between(text: str, start_kw: str, stop_kws: list) -> str:
    """取 start_kw 之后到任一 stop_kw 之前的子串（截断）。"""
    upper = text.upper()
    i = upper.find(start_kw)
    if i < 0:
        return ""
    j = i + len(start_kw)
    # 找最近出现的子句关键字
    stops = [upper.find(sk, j) for sk in stop_kws if upper.find(sk, j) >= 0]
    end = min(stops) if stops else len(text)
    raw = text[j:end].strip(" ,\t;")
    return _trunc(_compact(raw), 60)


def _limit(text: str) -> Optional[str]:
    m = re.search(r"\bLIMIT\s+([0-9]+)", text, re.IGNORECASE)
    return str(int(m.group(1))) if m else None


__all__ = ["describe_sql"]