"""
SQL错误分类器

位置：core/security/sql_error.py
职责：把数据库引擎抛出的原始错误信息分类成「可自纠」的结构化提示，
供工具层把错误+"修复建议"一起回喂给 LLM，减少盲目重试与臆造列名/表名。

纯逻辑模块：不触库、无副作用，便于脱离数据库单测。
作为 generate→execute→reflect 循环里「reflect」环节的错误反馈来源。
"""

import re
from typing import Dict, List, Tuple, Optional

# (错误码, 正则模式, 简洁摘要, 修复建议)。
# 建议文案面向 LLM 系统提示词，明确指引下一步动作。
_ERROR_RULES: List[Tuple[str, str, str, str]] = [
    (
        "column_not_found",
        r"column\s+(?:[^.\s]+\.)?[`\"]?([\w]+)[`\"]?\s+does\s+not\s+exist",
        "引用了不存在的列",
        "用 get_table_schema 核对真实列名与类型后修正 SELECT 列表/条件/聚合字段，不要臆造列名。",
    ),
    (
        "relation_not_found",
        r"(?:relation|table)\s+[`\"]?([\w.]+)[`\"]?\s+does\s+not\s+exist",
        "引用了不存在的表",
        "先用 get_relevant_schemas / list_tables 确认真实表名（含大小写），再修正 FROM/JOIN 目标。",
    ),
    (
        "ambiguous_column",
        r"column\s+reference\s+[`\"]?([\w]+)[`\"]?\s+is\s+ambiguous",
        "列引用有歧义（多表同名列）",
        "为该列加上表名或别名限定，如 t.<列名>，以消除歧义。",
    ),
    (
        "function_not_found",
        r"function\s+[\w.]+\([^)]*\)\s+does\s+not\s+exist",
        "使用不存在的函数或参数类型不匹配",
        "核对函数名及参数类型，必要时对参数做显式类型转换（如 ::numeric），或改用支持的函数。",
    ),
    (
        "syntax_error",
        r"syntax\s+error",
        "SQL 语法错误",
        "检查引号、括号、逗号与关键字拼写，必要时先看 get_table_schema 确认列名后重写。",
    ),
    (
        "division_by_zero",
        r"division\s+by\s+zero",
        "除数为零",
        "对除数加保护，例如 SUM(x)::numeric / NULLIF(SUM(y), 0)，或先用 WHERE 过滤 y 不为 0 的行。",
    ),
    (
        "duplicate_key",
        r"(?:duplicate\s+key\s+value|unique\s+constraint|ON\s+CONFLICT)",
        "违反唯一约束 / 重复主键",
        "检查写入数据是否与既有主键/唯一索引冲突，或改用 upsert（INSERT ... ON CONFLICT ... DO UPDATE）。",
    ),
    (
        "undefined_table",
        r"undefined\s+table",
        "引用了未定义/缺失的表",
        "核对表名是否存在，先 list_tables / get_relevant_schemas 确认目标表。",
    ),
    (
        "missing_from_clause",
        r"missing\s+FROM-clause\s+entry|from\s+clause\s+missing|is\s+missing\s+from\s+the\s+FROM",
        "查询中引用了未出现在 FROM 的表/列前缀",
        "为子查询/派生表的列加上别名或补全 FROM 目标表。",
    ),
    (
        "permission_denied",
        r"permission\s+denied|is\s+not\s+permitted",
        "权限不足",
        "当前连接缺少所需权限，请改用只读查询，或联系管理员开通权限。",
    ),
    (
        "invalid_type",
        r"cannot\s+be\s+coerced|invalid\s+input\sinteger|invalid\s+text\s+representation",
        "数据类型不匹配或非法输入",
        "核对列类型与传入值是否一致，必要时对值或列做显式类型转换（::）。",
    ),
    (
        "query_timeout",
        r"(?:timeout|cancel)ing\s+statement",
        "查询超时",
        "拆分复杂查询（减少 JOIN/子查询），缩小时间范围或增加 WHERE 过滤，或加 LIMIT 后再试。",
    ),
    (
        "group_by_error",
        r"must\s+appear\s+in\s+the\s+GROUP\s+BY|of\s+aggregate\s+function",
        "GROUP BY / 聚合使用错误",
        "GROUP BY 未包含的非聚合列需补进 GROUP BY，或对其用聚合函数包裹。",
    ),
]


def classify_sql_error(error: str) -> Dict[str, str]:
    """
    把原始错误信息分类为可自纠的结构化提示。

    返回:
        {"code", "summary", "suggestion"}。无法识别时返回兜底泛化建议。
    """
    text = error or ""
    text_lower = text.lower()

    for code, pattern, summary, suggestion in _ERROR_RULES:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return {
                "code": code,
                "summary": summary,
                "suggestion": suggestion,
            }

    return {
        "code": "unknown",
        "summary": "未知错误",
        "suggestion": "请核对表名/列名与类型是否与真实 schema 一致后重试；若仍失败，如实向用户报告该错误。",
    }


def extract_sqlstate(exc: Exception) -> Dict[str, str]:
    """
    从数据库驱动异常中提取结构化诊断(SQLSTATE + PostgreSQL diag)。

    返回 {"sqlstate", "message", "detail", "hint"}。无字段则返回空串。
    兼容 asyncpg(`.sqlstate`、`.diag`)；其他异常只取 str 兜底。
    """
    sqlstate = str(getattr(exc, 'sqlstate', '') or '')
    diag = getattr(exc, 'diag', None)
    message = getattr(exc, 'message', '') or ''

    detail = hint = ''
    if diag is not None:
        detail = str(getattr(diag, 'message_detail', '') or '')
        hint = str(getattr(diag, 'hint', '') or '')

    if not message:
        message = str(exc)

    return {
        "sqlstate": sqlstate,
        "message": message,
        "detail": detail,
        "hint": hint,
    }


def is_transient_error(exc: Exception) -> bool:
    """
    判断是否为「瞬时/可恢复」错误(值得官方中间件自动重试)。

    覆盖：连接中断/重置、死锁、串行化冲突、语句超时。非语法/逻辑类错误。
    """
    text = f"{getattr(exc, 'sqlstate', '')} {exc}".lower()
    for marker in ('57p01', '57p02', '57p03',  # admin_shutdown / cannot_connect / cannot_connect_now
                   '40p01', '40001',          # deadlock / serialization_failure
                   '57014', '55p03',          # query_canceled / lock_not_available
                   'connection', 'timeout', 'too many connections', 'reset'):
        if marker in text:
            return True
    return False


def build_self_correction_message(error: str, *, exc: Optional[Exception] = None) -> str:
    """
    把原始错误拼装成面向 LLM 的自纠反馈字符串。

    优先使用真实 SQLSTATE + detail(若有)，否则回退正则分类。形如：
        SQLSTATE[42883] [function_not_found] 使用不存在的函数...。
        原始错误: function foo(...) does not exist。detail: ...。修复建议: ...
    """
    info = classify_sql_error(error)

    head = f"[{info['code']}] {info['summary']}"
    state = getattr(exc, 'sqlstate', None) if exc is not None else None
    if state:
        head = f"SQLSTATE[{state}] " + head

    detail_part = ""
    if exc is not None:
        fields = extract_sqlstate(exc)
        if fields.get("detail"):
            detail_part = f" detail: {fields['detail']}"
        if fields.get("hint"):
            detail_part += f" hint: {fields['hint']}"

    return (
        f"{head}。原始错误: {error or '(空)'}{detail_part}。"
        f"修复建议: {info['suggestion']}"
    )


__all__ = ["classify_sql_error", "build_self_correction_message",
           "extract_sqlstate", "is_transient_error"]