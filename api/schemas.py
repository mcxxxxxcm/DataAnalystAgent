"""
API 响应模型

位置：api/schemas.py
职责：定义 API 的请求和响应模型
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ==================== 请求模型 ====================

class QueryRequest(BaseModel):
    """查询请求"""
    query: str = Field(description="用户的自然语言查询")
    thread_id: Optional[str] = Field(
        default=None,
        description="会话ID，用于多轮对话"
    )


class ApprovalRequest(BaseModel):
    """审核请求"""
    thread_id: str = Field(description="会话ID")
    decision: str = Field(
        description="决策类型: approve, reject",
        pattern="^(approve|reject)$"
    )
    reason: Optional[str] = Field(
        default=None,
        description="拒绝原因（reject时使用）"
    )


# ==================== 响应模型 ====================

class QueryResponse(BaseModel):
    """查询响应"""
    success: bool = Field(description="是否成功")
    thread_id: str = Field(description="会话ID")
    message: Optional[str] = Field(
        default=None,
        description="响应消息"
    )
    data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="查询结果数据"
    )
    sql: Optional[str] = Field(
        default=None,
        description="执行的SQL语句"
    )
    charts: Optional[List[str]] = Field(
        default=None,
        description="图表列表（base64编码）"
    )
    requires_approval: bool = Field(
        default=False,
        description="是否需要人工审核"
    )
    approval_request: List[Any] = Field(
        default=None,
        description="审核请求详情"
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息"
    )
    execution_time_ms: float = Field(
        default=0.0,
        description="执行时间（毫秒）"
    )


class ApprovalResponse(BaseModel):
    """审核响应"""
    success: bool
    thread_id: str
    message: str
    result: Optional[Dict[str, Any]] = None


class StateResponse(BaseModel):
    """状态响应"""
    thread_id: str
    state: Optional[Dict[str, Any]] = None
    next_steps: List[str] = []


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: str
    version: str
    database_connected: bool


class LogResponse(BaseModel):
    """日志响应"""
    records: List[Dict[str, Any]]
    total: int


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())