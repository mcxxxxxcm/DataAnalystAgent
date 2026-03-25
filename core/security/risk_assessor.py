"""
风险评估器

位置：core/security/risk_assessor.py
职责：评估操作风险等级，决定是否需要人工审核

评估维度：
1. SQL复杂度
2. 影响范围
3. 数据敏感性
4. 操作类型
"""

from typing import Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from .sql_validator import SQLRiskLevel
from .sql_sanitizer import sql_sanitizer


class RiskFactor(Enum):
    """风险因素"""
    HIGH_COMPLEXITY = "high_complexity"  # 高复杂度
    LARGE_TABLE = "large_table"  # 大表操作
    WRITE_OPERATION = "write_operation"  # 写操作
    NO_WHERE_CLAUSE = "no_where_clause"  # 无WHERE条件
    MULTI_TABLE = "multi_table"  # 多表操作
    SENSITIVE_TABLE = "sensitive_table"  # 敏感表


@dataclass
class RiskAssessment:
    """风险评估结果"""
    risk_level: SQLRiskLevel
    requires_approval: bool
    risk_factors: List[RiskFactor]
    confidence: float
    explanation: str
    recommendations: List[str]


class RiskAssessor:
    """
    风险评估器

    决定操作是否需要人工审核

    评估逻辑：
    1. CRITICAL: 禁止执行
    2. HIGH: 必须人工审核
    3. MEDIUM: 建议人工审核
    4. LOW: 可自动执行，记录日志
    5. SAFE: 可自动执行
    """

    # 敏感表（需要特殊审核）
    SENSITIVE_TABLES = {
        'users', 'accounts', 'payments', 'transactions',
        'credentials', 'secrets', 'configs', 'settings'
    }

    # 大表阈值（行数）
    LARGE_TABLE_THRESHOLD = 100000

    def __init__(
            self,
            auto_approve_safe: bool = True,
            auto_approve_low: bool = True,
            require_approval_medium: bool = True
    ):
        """
        初始化风险评估器

        参数:
            auto_approve_safe: 是否自动批准SAFE级别
            auto_approve_low: 是否自动批准LOW级别
            require_approval_medium: MEDIUM级别是否需要审核
        """
        self.auto_approve_safe = auto_approve_safe
        self.auto_approve_low = auto_approve_low
        self.require_approval_medium = require_approval_medium

    def assess(self, sql: str, validator_result=None) -> RiskAssessment:
        """
        执行风险评估
        """
        risk_factors = []
        recommendations = []

        # 获取SQL复杂度
        complexity = sql_sanitizer.estimate_complexity(sql)
        sql_upper = sql.upper()

        # 评估各项风险因素

        # 1. 复杂度评估
        if complexity['estimated_cost'] == 'high':
            risk_factors.append(RiskFactor.HIGH_COMPLEXITY)
            recommendations.append("查询复杂度高，建议简化或分步执行")

        # 2. 多表操作
        if complexity['table_count'] > 2:
            risk_factors.append(RiskFactor.MULTI_TABLE)
            recommendations.append(f"涉及{complexity['table_count']}个表，请确认关联关系正确")

        # 3. 写操作
        is_write = any(kw in sql_upper for kw in ['INSERT', 'UPDATE', 'DELETE'])
        if is_write:
            risk_factors.append(RiskFactor.WRITE_OPERATION)
            recommendations.append("这是写操作，请确认影响范围")

        # 4. 无WHERE条件
        if is_write and 'WHERE' not in sql_upper:
            risk_factors.append(RiskFactor.NO_WHERE_CLAUSE)
            recommendations.append("写操作缺少WHERE条件，将影响全表！")

        # 5. 敏感表
        tables = sql_sanitizer.extract_tables(sql)
        sensitive_tables = [t for t in tables if t.lower() in self.SENSITIVE_TABLES]
        if sensitive_tables:
            risk_factors.append(RiskFactor.SENSITIVE_TABLE)
            recommendations.append(f"涉及敏感表: {', '.join(sensitive_tables)}")

        # 确定最终风险等级
        risk_level = self._determine_risk_level(risk_factors, complexity)

        # 确定是否需要审核
        requires_approval = self._requires_approval(risk_level, risk_factors)

        # 生成解释
        explanation = self._generate_explanation(risk_level, risk_factors)

        return RiskAssessment(
            risk_level=risk_level,
            requires_approval=requires_approval,
            risk_factors=risk_factors,
            confidence=0.85,  # 基于规则的评估置信度
            explanation=explanation,
            recommendations=recommendations
        )

    def _determine_risk_level(
            self,
            risk_factors: List[RiskFactor],
            complexity: Dict[str, Any]
    ) -> SQLRiskLevel:
        """确定风险等级"""
        # CRITICAL: 无WHERE条件的写操作
        if RiskFactor.NO_WHERE_CLAUSE in risk_factors:
            return SQLRiskLevel.CRITICAL

        # HIGH: 写操作或敏感表
        if RiskFactor.WRITE_OPERATION in risk_factors or RiskFactor.SENSITIVE_TABLE in risk_factors:
            return SQLRiskLevel.HIGH

        # MEDIUM: 高复杂度或多表
        if RiskFactor.HIGH_COMPLEXITY in risk_factors or RiskFactor.MULTI_TABLE in risk_factors:
            return SQLRiskLevel.MEDIUM

        # LOW: 有一些风险因素
        if risk_factors:
            return SQLRiskLevel.LOW

        # SAFE: 无风险因素
        return SQLRiskLevel.SAFE

    def _requires_approval(
            self,
            risk_level: SQLRiskLevel,
            risk_factors: List[RiskFactor]
    ) -> bool:
        """判断是否需要人工审核"""
        if risk_level == SQLRiskLevel.CRITICAL:
            return True  # 实际上应该禁止执行

        if risk_level == SQLRiskLevel.HIGH:
            return True

        if risk_level == SQLRiskLevel.MEDIUM:
            return self.require_approval_medium

        if risk_level == SQLRiskLevel.LOW:
            return not self.auto_approve_low

        return False  # SAFE级别

    def _generate_explanation(
            self,
            risk_level: SQLRiskLevel,
            risk_factors: List[RiskFactor]
    ) -> str:
        """生成风险解释"""
        level_descriptions = {
            SQLRiskLevel.SAFE: "此查询安全，可以自动执行",
            SQLRiskLevel.LOW: "此查询风险较低，建议检查后执行",
            SQLRiskLevel.MEDIUM: "此查询有一定风险，建议人工审核",
            SQLRiskLevel.HIGH: "此查询风险较高，必须人工审核",
            SQLRiskLevel.CRITICAL: "此查询风险极高，建议禁止执行"
        }

        base_explanation = level_descriptions[risk_level]

        if risk_factors:
            factors_str = "、".join([f.value for f in risk_factors])
            return f"{base_explanation}。风险因素: {factors_str}"

        return base_explanation


# 默认实例
risk_assessor = RiskAssessor()