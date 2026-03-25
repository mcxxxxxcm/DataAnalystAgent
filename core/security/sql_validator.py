"""
SQL安全校验器

位置：core/security/sql_validator.py
职责：校验SQL安全性，防止恶意操作

为什么需要SQL校验：
1. LLM生成的SQL可能包含危险操作
2. 防止SQL注入攻击
3. 防止误删数据
4. 生产环境必须有防御性编程

校验策略：
1. AST解析：使用sqlparse解析语法树，比正则更可靠
2. 白名单机制：只允许SELECT（可配置）
3. 黑名单检测：禁止DROP、DELETE等危险操作
4. 函数检测：禁止危险函数
"""

import sqlparse
from sqlparse.sql import Statement, Token
from sqlparse.tokens import DML, Keyword
from typing import Tuple, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import re

from config.settings import get_settings


class SQLRiskLevel(Enum):
    """SQL风险等级"""
    SAFE = "safe"  # 安全，可直接执行
    LOW = "low"  # 低风险，建议审核
    MEDIUM = "medium"  # 中风险，需要审核
    HIGH = "high"  # 高风险，必须审核
    CRITICAL = "critical"  # 危险，禁止执行


class SQLErrorType(Enum):
    """SQL错误类型"""
    FORBIDDEN_KEYWORD = "forbidden_keyword"
    FORBIDDEN_FUNCTION = "forbidden_function"
    FORBIDDEN_OPERATION = "forbidden_operation"
    SYNTAX_ERROR = "syntax_error"
    INJECTION_ATTEMPT = "injection_attempt"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    risk_level: SQLRiskLevel
    sanitized_sql: Optional[str] = None
    error_type: Optional[SQLErrorType] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    detected_issues: List[str] = field(default_factory=list)


class SQLValidator:
    """
    SQL安全校验器

    多层校验策略：
    1. 语法解析层：AST解析，检测DML类型
    2. 关键字黑名单：禁止危险关键字
    3. 函数黑名单：禁止危险函数
    4. 注入检测：检测常见的注入模式
    5. 权限检查：根据配置检查操作权限
    """

    # 允许的DML操作（白名单）
    ALLOWED_DML: Set[str] = {'SELECT'}

    # 禁止的关键字（黑名单）
    FORBIDDEN_KEYWORDS: Set[str] = {
        'DROP', 'TRUNCATE', 'ALTER', 'CREATE',
        'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
        'INTO OUTFILE', 'INTO DUMPFILE', 'LOAD_FILE'
    }

    # 写操作关键字（需要权限检查）
    WRITE_KEYWORDS: Set[str] = {'INSERT', 'UPDATE', 'DELETE'}

    # 禁止的函数
    FORBIDDEN_FUNCTIONS: Set[str] = {
        'load_file', 'into outfile', 'into dumpfile',
        'sys_exec', 'sys_eval', 'sleep', 'benchmark',
        'pg_read_file', 'pg_write_file', 'pg_ls_dir',
        'copy', 'lo_import', 'lo_export'
    }

    # 危险注释模式（注入检测）
    DANGEROUS_COMMENT_PATTERNS: List[str] = [
        r'--\s*(drop|delete|truncate|insert|update)',
        r'/\*.*?(drop|delete|truncate|insert|update).*?\*/',
        r'#\s*(drop|delete|truncate|insert|update)',
    ]

    def __init__(
            self,
            max_rows: int = 10000,
            enable_write: bool = False,
            timeout: int = 30
    ):
        """
        初始化校验器

        参数:
            max_rows: 最大返回行数
            enable_write: 是否允许写操作
            timeout: 查询超时时间
        """
        self.max_rows = max_rows
        self.enable_write = enable_write
        self.timeout = timeout

        # 如果允许写操作，更新白名单
        if enable_write:
            self.ALLOWED_DML = {'SELECT', 'INSERT', 'UPDATE', 'DELETE'}

    def validate(self, sql: str) -> ValidationResult:
        """
        主校验入口

        执行多层校验，任何一层失败都会拒绝SQL
        """
        warnings = []
        detected_issues = []

        # 第一层：基础检查
        if not sql or not sql.strip():
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.CRITICAL,
                error_type=SQLErrorType.SYNTAX_ERROR,
                error_message="SQL语句为空"
            )

        # 第二层：语法解析
        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                return ValidationResult(
                    is_valid=False,
                    risk_level=SQLRiskLevel.CRITICAL,
                    error_type=SQLErrorType.SYNTAX_ERROR,
                    error_message="无法解析SQL语句"
                )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.CRITICAL,
                error_type=SQLErrorType.SYNTAX_ERROR,
                error_message=f"SQL解析错误: {str(e)}"
            )

        statement = parsed[0]

        # 第三层：DML类型检查
        dml_type = self._get_dml_type(statement)

        if dml_type not in self.ALLOWED_DML:
            detected_issues.append(f"不允许的操作类型: {dml_type}")
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.CRITICAL,
                error_type=SQLErrorType.FORBIDDEN_OPERATION,
                error_message=f"不允许的操作类型: {dml_type}。只允许: {self.ALLOWED_DML}"
            )

        # 第四层：关键字黑名单检查
        forbidden_keywords = self._check_forbidden_keywords(sql)
        if forbidden_keywords:
            detected_issues.extend(forbidden_keywords)
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.CRITICAL,
                error_type=SQLErrorType.FORBIDDEN_KEYWORD,
                error_message=f"检测到禁止的关键字: {', '.join(forbidden_keywords)}"
            )

        # 第五层：危险函数检查
        forbidden_funcs = self._check_forbidden_functions(sql)
        if forbidden_funcs:
            detected_issues.extend(forbidden_funcs)
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.CRITICAL,
                error_type=SQLErrorType.FORBIDDEN_FUNCTION,
                error_message=f"检测到禁止的函数: {', '.join(forbidden_funcs)}"
            )

        # 第六层：注入检测
        injection_detected = self._detect_injection(sql)
        if injection_detected:
            detected_issues.append("检测到可能的SQL注入模式")
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.CRITICAL,
                error_type=SQLErrorType.INJECTION_ATTEMPT,
                error_message="SQL包含可疑的注入模式"
            )

        # 第七层：风险评估
        risk_level = self._assess_risk(sql, dml_type)

        # 第八层：权限检查
        if dml_type in self.WRITE_KEYWORDS and not self.enable_write:
            return ValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.HIGH,
                error_type=SQLErrorType.PERMISSION_DENIED,
                error_message=f"写操作({dml_type})未启用，请设置 enable_sql_write=True"
            )

        # 添加警告信息
        if dml_type == 'SELECT':
            warnings.append(f"查询超时设置为{self.timeout}秒")
            if 'JOIN' in sql.upper():
                join_count = sql.upper().count('JOIN')
                if join_count > 3:
                    warnings.append(f"查询包含{join_count}个JOIN，可能较慢")

        return ValidationResult(
            is_valid=True,
            risk_level=risk_level,
            warnings=warnings,
            detected_issues=detected_issues
        )

    def _get_dml_type(self, statement: Statement) -> str:
        """
        获取DML操作类型

        使用sqlparse的token类型判断，比正则更准确
        """
        for token in statement.flatten():
            if token.ttype is DML:
                return token.value.upper()
        return 'UNKNOWN'

    def _check_forbidden_keywords(self, sql: str) -> List[str]:
        """检查禁止的关键字"""
        sql_upper = sql.upper()
        found = []

        for keyword in self.FORBIDDEN_KEYWORDS:
            # 使用单词边界匹配
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, sql_upper):
                found.append(keyword)

        return found

    def _check_forbidden_functions(self, sql: str) -> List[str]:
        """检查禁止的函数"""
        sql_lower = sql.lower()
        found = []

        for func in self.FORBIDDEN_FUNCTIONS:
            if func in sql_lower:
                found.append(func)

        return found

    def _detect_injection(self, sql: str) -> bool:
        """
        检测SQL注入模式

        检测常见的注入技巧：
        1. 注释后跟危险语句
        2. 字符串拼接
        3. 多语句注入
        """
        sql_lower = sql.lower()

        # 检查危险注释模式
        for pattern in self.DANGEROUS_COMMENT_PATTERNS:
            if re.search(pattern, sql_lower, re.IGNORECASE | re.DOTALL):
                return True

        # 检查多语句（分号分隔）
        statements = sqlparse.split(sql)
        if len(statements) > 1:
            # 检查第二个语句是否是危险操作
            for stmt in statements[1:]:
                if stmt.strip():
                    parsed = sqlparse.parse(stmt)
                    if parsed:
                        dml = self._get_dml_type(parsed[0])
                        if dml in self.FORBIDDEN_KEYWORDS or dml in self.WRITE_KEYWORDS:
                            return True

        return False

    def _assess_risk(self, sql: str, dml_type: str) -> SQLRiskLevel:
        """
        评估SQL风险等级

        风险等级判断标准：
        - SAFE: 简单SELECT，单表
        - LOW: SELECT with JOIN
        - MEDIUM: 复杂SELECT（子查询、聚合）
        - HIGH: 写操作
        - CRITICAL: 危险操作（已在前面的检查中拒绝）
        """
        sql_upper = sql.upper()

        if dml_type == 'SELECT':
            # 检查复杂度
            has_join = 'JOIN' in sql_upper
            has_subquery = sql_upper.count('SELECT') > 1
            has_aggregation = any(kw in sql_upper for kw in ['GROUP BY', 'HAVING', 'DISTINCT'])

            if has_subquery and has_join:
                return SQLRiskLevel.MEDIUM
            elif has_join or has_aggregation:
                return SQLRiskLevel.LOW
            else:
                return SQLRiskLevel.SAFE

        elif dml_type in self.WRITE_KEYWORDS:
            return SQLRiskLevel.HIGH

        return SQLRiskLevel.LOW


# 从配置创建默认实例
def create_validator() -> SQLValidator:
    """根据配置创建校验器实例"""
    settings = get_settings()
    return SQLValidator(
        max_rows=settings.sql_max_rows,
        enable_write=settings.enable_sql_write,
        timeout=settings.sql_timeout
    )


# 默认实例
sql_validator = create_validator()