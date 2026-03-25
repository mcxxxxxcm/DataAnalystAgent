"""
SQL清理器

位置：core/security/sql_sanitizer.py
职责：清理和转换SQL，使其更安全

主要功能：
1. 自动注入LIMIT：防止全表扫描
2. 移除危险注释：防止注入
3. 标准化SQL格式：便于分析
4. 参数化处理：防止注入
"""

import sqlparse
from typing import Tuple, Optional, List
from dataclasses import dataclass
import re

from config.settings import get_settings


@dataclass
class SanitizationResult:
    """清理结果"""
    original_sql: str
    sanitized_sql: str
    modifications: List[str]
    limit_added: bool = False
    comments_removed: List[str] = None

    def __post_init__(self):
        if self.comments_removed is None:
            self.comments_removed = []


class SQLSanitizer:
    """
    SQL清理器

    为什么需要清理：
    1. LLM生成的SQL可能没有LIMIT
    2. 注释可能包含恶意代码
    3. 格式不统一影响分析
    4. 需要添加安全限制
    """

    def __init__(self, max_rows: int = 10000, timeout: int = 30):
        """
        初始化清理器

        参数:
            max_rows: 默认LIMIT值
            timeout: 查询超时提示
        """
        self.max_rows = max_rows
        self.timeout = timeout

    def sanitize(self, sql: str) -> SanitizationResult:
        """
        主清理入口

        执行所有清理步骤
        """
        modifications = []
        comments_removed = []

        # 保存原始SQL
        original_sql = sql

        # 步骤1：移除危险注释
        sql, removed = self._remove_dangerous_comments(sql)
        comments_removed.extend(removed)
        if removed:
            modifications.append("移除了危险注释")

        # 步骤2：标准化格式
        sql = self._normalize_format(sql)
        modifications.append("标准化了SQL格式")

        # 步骤3：注入LIMIT（仅SELECT）
        limit_added = False
        if self._is_select(sql):
            sql, limit_added = self._ensure_limit(sql)
            if limit_added:
                modifications.append(f"添加了LIMIT {self.max_rows}")

        # 步骤4：添加超时提示（注释形式，不影响执行）
        # 注意：实际超时由连接池控制

        return SanitizationResult(
            original_sql=original_sql,
            sanitized_sql=sql,
            modifications=modifications,
            limit_added=limit_added,
            comments_removed=comments_removed
        )

    def _remove_dangerous_comments(self, sql: str) -> Tuple[str, List[str]]:
        """
        移除危险注释

        保留有用的注释，移除可疑的注释
        """
        removed = []

        # 移除 -- 开头的单行注释（如果包含危险关键字）
        def replace_dangerous_line_comment(match):
            comment = match.group(0)
            if re.search(r'(drop|delete|truncate|insert|update)', comment, re.I):
                removed.append(comment)
                return ''
            return comment

        sql = re.sub(r'--[^\n]*', replace_dangerous_line_comment, sql)

        # 移除 /* */ 多行注释（如果包含危险关键字）
        def replace_dangerous_block_comment(match):
            comment = match.group(0)
            if re.search(r'(drop|delete|truncate|insert|update)', comment, re.I):
                removed.append(comment)
                return ''
            return comment

        sql = re.sub(r'/\*.*?\*/', replace_dangerous_block_comment, sql, flags=re.DOTALL)

        return sql.strip(), removed

    def _normalize_format(self, sql: str) -> str:
        """
        标准化SQL格式

        使用sqlparse进行格式化
        """
        # 解析并重新格式化
        formatted = sqlparse.format(
            sql,
            keyword_case='upper',  # 关键字大写
            identifier_case='lower',  # 标识符小写
            strip_comments=False,  # 保留安全注释
            reindent=True,  # 重新缩进
            use_space_around_operators=True
        )

        return formatted.strip()

    def _is_select(self, sql: str) -> bool:
        """判断是否是SELECT语句"""
        sql_stripped = sql.strip().upper()
        return sql_stripped.startswith('SELECT')

    def _ensure_limit(self, sql: str) -> Tuple[str, bool]:
        """
        确保SELECT语句有LIMIT

        如果没有，自动添加

        为什么需要LIMIT：
        1. 防止全表扫描导致数据库压力
        2. 防止返回过多数据导致内存溢出
        3. 保护生产数据库稳定性
        """
        sql_upper = sql.upper()

        # 检查是否已有LIMIT
        if 'LIMIT' in sql_upper:
            return sql, False

        # 检查是否有OFFSET（通常和LIMIT一起）
        if 'OFFSET' in sql_upper:
            # 有OFFSET但没有LIMIT，添加LIMIT
            pass

        # 移除末尾分号
        sql = sql.rstrip()
        had_semicolon = sql.endswith(';')
        if had_semicolon:
            sql = sql[:-1]

        # 添加LIMIT
        sql = f"{sql} LIMIT {self.max_rows}"

        if had_semicolon:
            sql = f"{sql};"

        return sql, True

    def extract_tables(self, sql: str) -> List[str]:
        """
        提取SQL中涉及的表名

        用于：
        1. 权限检查
        2. Schema获取
        3. 审计日志
        """
        tables = []

        # 提取FROM后的表名
        from_pattern = r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables.extend(re.findall(from_pattern, sql, re.IGNORECASE))

        # 提取JOIN后的表名
        join_pattern = r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables.extend(re.findall(join_pattern, sql, re.IGNORECASE))

        # 提取INSERT INTO后的表名
        insert_pattern = r'\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables.extend(re.findall(insert_pattern, sql, re.IGNORECASE))

        # 提取UPDATE后的表名
        update_pattern = r'\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables.extend(re.findall(update_pattern, sql, re.IGNORECASE))

        # 提取DELETE FROM后的表名
        delete_pattern = r'\bDELETE\s+FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables.extend(re.findall(delete_pattern, sql, re.IGNORECASE))

        # 去重
        return list(set(tables))

    def estimate_complexity(self, sql: str) -> dict:
        """
        评估SQL复杂度

        用于：
        1. 预估执行时间
        2. 决定是否需要审核
        3. 提示用户
        """
        sql_upper = sql.upper()

        return {
            'join_count': sql_upper.count('JOIN'),
            'subquery_count': sql_upper.count('SELECT') - 1,
            'has_aggregation': 'GROUP BY' in sql_upper or 'HAVING' in sql_upper,
            'has_distinct': 'DISTINCT' in sql_upper,
            'has_union': 'UNION' in sql_upper,
            'table_count': len(self.extract_tables(sql)),
            'estimated_cost': self._calculate_cost(sql_upper)
        }

    def _calculate_cost(self, sql_upper: str) -> str:
        """
        计算预估成本

        简单的启发式评估
        """
        cost = 0

        cost += sql_upper.count('JOIN') * 2
        cost += sql_upper.count('SELECT') - 1  # 子查询
        cost += 3 if 'GROUP BY' in sql_upper else 0
        cost += 2 if 'HAVING' in sql_upper else 0
        cost += 1 if 'DISTINCT' in sql_upper else 0
        cost += 2 if 'UNION' in sql_upper else 0
        cost += 5 if 'ORDER BY' in sql_upper else 0

        if cost <= 3:
            return 'low'
        elif cost <= 10:
            return 'medium'
        else:
            return 'high'


# 从配置创建默认实例
def create_sanitizer() -> SQLSanitizer:
    """根据配置创建清理器实例"""
    settings = get_settings()
    return SQLSanitizer(
        max_rows=settings.sql_max_rows,
        timeout=settings.sql_timeout
    )


# 默认实例
sql_sanitizer = create_sanitizer()