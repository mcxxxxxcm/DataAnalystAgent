"""
工具边界校验层

位置：tools/boundaries.py
职责：集中所有"工具安全边界"的校验逻辑，供各 tool 复用，也便于脱离数据库单测。

覆盖：
- 表名白名单校验（标识符合法性 + 必须属于 schema_manager 白名单）
- 禁止访问系统表（checkpoint / conversations 等）
- query_database 的统一 SQL 守卫（复用 core/security 的 validator + sanitizer）

为什么集中：
- 原先 SQL 校验只存在于 export_result，query_database 完全绕过安全层。
- 表名白名单散落在 analysis_tools，而 sql_tools 的表名无校验。
- 收敛到一个模块，避免重复、避免双份系统表清单漂移。
"""

import re
from typing import Any

from config.settings import get_settings
from core.database import schema_manager
# 注意：必须从子模块导入"实例"而非 `core.security` 包名——
# core.security.__getattr__ 懒加载实例会被同名子模块遮蔽，包名取到的是 module。
from core.security.sql_validator import sql_validator
from core.security.sql_sanitizer import sql_sanitizer

# 系统表（/schema, 会话, 缓存等），禁止直接查询。与 core/database/schema.py 保持一致。
SYSTEM_TABLES: set[str] = {
    'checkpoint_blobs', 'checkpoint_migrations', 'checkpoint_writes',
    'checkpoints', 'conversations', 'messages', 'tool_calls',
    'query_cache', 'report_templates'
}

# 合法标识符：字母/数字/下划线，防止表名列名注入
_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_]+$')


async def is_allowed_table(table_name: str) -> str:
    """
    校验表名在白名单内并返回规范化表名。

    抛 ValueError 表示表名非法或表不存在/属于系统表。
    """
    if not table_name or not _IDENTIFIER_RE.match(table_name):
        raise ValueError(f"非法表名: {table_name!r}")
    if table_name in SYSTEM_TABLES:
        raise ValueError(f"禁止查询系统表: {table_name}")
    tables = await schema_manager.list_tables()
    if table_name not in tables:
        raise ValueError(f"表不存在: {table_name}，可用表: {sorted(tables)}")
    return table_name


def extract_sql_tables(sql: str, sanitizer: Any = None) -> list[str]:
    """提取 SQL 中涉及的（非系统）表名。不触库。sanitizer 便于测试注入。"""
    sanitizer = sanitizer or sql_sanitizer
    return [t for t in sanitizer.extract_tables(sql) if t not in SYSTEM_TABLES]


async def guard_query_sql(
    query: str,
    *,
    validator: Any = None,
    sanitizer: Any = None,
    table_checker: Any = None,
) -> tuple[str, str | None]:
    """
    执行查询前的统一边界守卫（不触库）。

    依赖默认取全局实例（与配置 enable_sql_write 一致）；可通过参数注入以便单测。

    返回 (sql, error)：
    - 校验/白名单通过 → (sanitized_sql, None)；sanitized_sql 已含 LIMIT 钳制与清理。
    - 校验失败 → (原 query, 错误信息)。
    """
    validator = validator or sql_validator
    sanitizer = sanitizer or sql_sanitizer

    if not query or not str(query).strip():
        return query, "SQL 语句为空"

    # 1. 安全校验（写操作是否放行取决于配置 enable_sql_write）
    validation = validator.validate(str(query))
    if not validation.is_valid:
        return query, f"SQL 校验失败: {validation.error_message}"

    # 2. 表名边界：命中系统表或不在白名单 → 拒绝
    checker = table_checker or is_allowed_table
    for table in sanitizer.extract_tables(str(query)):
        try:
            await checker(table)
        except ValueError as e:
            return query, f"查询涉及不允许的表: {e}"

    # 3. 清理：规范化 + 自动 LIMIT（钳制到 sql_max_rows）
    sanitized = sanitizer.sanitize(str(query))
    return sanitized.sanitized_sql, None


def max_select_rows() -> int:
    """查询最大返回行数（security/sanitizer 与限制一致）。"""
    return get_settings().sql_max_rows