"""
API 路由

位置：api/routes.py
职责：定义所有 API 端点
"""

import uuid
import time
from typing import AsyncIterator, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import json

from middleware import local_logger
from core.database import db_pool
from .schemas import (
    QueryRequest, QueryResponse,
    ApprovalRequest, ApprovalResponse,
    StateResponse, HealthResponse,
    LogResponse, ErrorResponse
)

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    执行自然语言查询

    流程：
    1. 创建或使用现有会话
    2. Agent 处理查询
    3. 检查是否需要人工审核
    4. 返回结果
    """
    from agent import get_agent
    
    start_time = time.time()
    thread_id = request.thread_id or str(uuid.uuid4())

    try:
        agent = get_agent()
        config = {"configurable": {"thread_id": thread_id}}

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": request.query}]},
            config=config
        )

        if "__interrupt__" in result:
            interrupt_data = result["__interrupt__"]
            return QueryResponse(
                success=False,
                thread_id=thread_id,
                requires_approval=True,
                approval_request=interrupt_data,
                message="此操作需要人工审核"
            )

        messages = result.get("messages", [])
        last_message = messages[-1] if messages else None

        return QueryResponse(
            success=True,
            thread_id=thread_id,
            message=last_message.content if last_message else None,
            execution_time_ms=(time.time() - start_time) * 1000
        )

    except Exception as e:
        return QueryResponse(
            success=False,
            thread_id=thread_id,
            error=str(e),
            execution_time_ms=(time.time() - start_time) * 1000
        )


@router.post("/approve", response_model=ApprovalResponse)
async def approve(request: ApprovalRequest):
    """
    处理人工审核

    用户审核后继续执行
    """
    from agent import handle_interrupt
    
    try:
        result = await handle_interrupt(
            thread_id=request.thread_id,
            decision=request.decision,
            message=request.reason
        )

        messages = result.get("messages", [])
        last_message = messages[-1] if messages else None

        return ApprovalResponse(
            success=True,
            thread_id=request.thread_id,
            message="审核已处理" if request.decision == "approve" else "操作已拒绝",
            result={"message": last_message.content if last_message else None}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{thread_id}", response_model=StateResponse)
async def get_state(thread_id: str):
    """
    获取会话状态

    用于调试和查看执行状态
    """
    from agent import get_agent
    
    try:
        agent = get_agent()
        config = {"configurable": {"thread_id": thread_id}}

        state = await agent.aget_state(config)

        return StateResponse(
            thread_id=thread_id,
            state=state.values if state else None,
            next_steps=list(state.next) if state and state.next else []
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查

    检查服务和数据库连接状态
    """
    db_connected = await db_pool.health_check()

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        version="1.0.0",
        database_connected=db_connected
    )


@router.get("/logs", response_model=LogResponse)
async def get_logs(
        limit: int = Query(default=10, ge=1, le=100),
        tool_name: Optional[str] = Query(default=None)
):
    """
    获取日志记录

    从本地日志中读取
    """
    if tool_name:
        records = local_logger.query_records(tool_name=tool_name)
    else:
        records = local_logger.get_recent_records(limit)

    return LogResponse(
        records=records[:limit],
        total=len(records)
    )


@router.get("/stream/{thread_id}")
async def stream_response(thread_id: str, query: str):
    """
    流式响应

    实时返回 Agent 执行进度
    """
    from agent import get_agent

    async def generate() -> AsyncIterator[str]:
        agent = get_agent()
        config = {"configurable": {"thread_id": thread_id}}

        async for event in agent.astream(
                {"messages": [{"role": "user", "content": query}]},
                config=config,
                stream_mode=["updates", "messages"]
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
