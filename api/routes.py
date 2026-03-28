"""
API 路由

位置：api/routes.py
职责：定义所有 API 端点
支持短期记忆（多轮对话上下文保持）
"""

import uuid
import time
import hashlib
from typing import AsyncIterator, Optional, List, Any, Dict
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

CHART_TOOL_NAMES = {'create_line_chart', 'create_bar_chart', 'create_pie_chart'}


def extract_chart_data(messages: List[Any]) -> Optional[Dict[str, Any]]:
    """
    从消息列表中提取图表数据
    
    Args:
        messages: Agent 返回的消息列表
        
    Returns:
        图表数据字典或 None
    """
    for msg in reversed(messages):
        msg_type = type(msg).__name__
        
        if msg_type == 'ToolMessage':
            try:
                content = getattr(msg, 'content', '{}')
                if isinstance(content, str):
                    tool_result = json.loads(content)
                else:
                    tool_result = content if isinstance(content, dict) else {}
                
                if tool_result.get('image_base64'):
                    return tool_result
            except (json.JSONDecodeError, TypeError):
                pass
        
        msg_name = getattr(msg, 'name', None)
        if msg_name in CHART_TOOL_NAMES:
            try:
                content = getattr(msg, 'content', '{}')
                if isinstance(content, str):
                    tool_result = json.loads(content)
                else:
                    tool_result = content if isinstance(content, dict) else {}
                
                if tool_result.get('image_base64'):
                    return tool_result
            except (json.JSONDecodeError, TypeError):
                pass
        
        artifact = getattr(msg, 'artifact', None)
        if artifact and isinstance(artifact, dict):
            if artifact.get('image_base64'):
                return artifact
    
    return None


def extract_all_chart_data(messages: List[Any]) -> List[Dict[str, Any]]:
    """
    从消息列表中提取所有图表数据（去重）
    
    Args:
        messages: Agent 返回的消息列表
        
    Returns:
        图表数据列表（已去重）
    """
    charts = []
    seen_chart_ids = set()
    
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        msg_name = getattr(msg, 'name', None)
        
        # 只处理 ToolMessage，避免重复处理
        if msg_type == 'ToolMessage':
            content = getattr(msg, 'content', None)
            
            if isinstance(content, str):
                try:
                    tool_result = json.loads(content)
                    if isinstance(tool_result, dict) and tool_result.get('image_base64'):
                        chart_type = tool_result.get('chart_type', 'unknown')
                        message = tool_result.get('message', '')
                        
                        # 使用 chart_type + message 的完整内容 + image_base64 的前50字符作为唯一标识
                        image_base64 = tool_result.get('image_base64', '')
                        chart_id = f"{chart_type}_{hashlib.md5((message + image_base64[:50]).encode()).hexdigest()}"
                        
                        if chart_id not in seen_chart_ids:
                            charts.append(tool_result)
                            seen_chart_ids.add(chart_id)
                            print(f"[DEBUG] Added chart {len(charts)}: type={chart_type}")
                        else:
                            print(f"[DEBUG] Skipped duplicate chart: type={chart_type}")
                except:
                    pass
    
    print(f"[DEBUG] Total charts found: {len(charts)} (after deduplication)")
    return charts


def get_message_content(msg: Any) -> str:
    """
    从消息对象中提取文本内容
    
    Args:
        msg: 消息对象
        
    Returns:
        消息文本内容
    """
    if msg is None:
        return ""
    
    if hasattr(msg, 'content') and msg.content:
        content = msg.content
        if isinstance(content, str):
            return content.strip()
        elif isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                elif isinstance(item, str):
                    text_parts.append(item)
            return '\n'.join(text_parts).strip()
    
    if hasattr(msg, 'text') and msg.text:
        return msg.text.strip()
    
    return str(msg).strip() if msg else ""


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    执行自然语言查询

    流程：
    1. 创建或使用现有会话
    2. Agent 处理查询（支持短期记忆，相同 thread_id 保持上下文）
    3. 检查是否需要人工审核
    4. 返回结果

    短期记忆说明：
    - 使用相同的 thread_id 可以保持多轮对话上下文
    - 例如：用户先问"上个月销售额"，再问"那前年同期呢？"
    - Agent 会记住之前的上下文，理解"那"指代的是"销售额"
    """
    from agent import get_async_agent

    start_time = time.time()
    thread_id = request.thread_id or str(uuid.uuid4())

    try:
        agent = await get_async_agent()
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

        chart_data = extract_chart_data(messages)

        return QueryResponse(
            success=True,
            thread_id=thread_id,
            message=last_message.content if last_message else None,
            chart_data=chart_data,
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

        all_charts = extract_all_chart_data(messages)
        chart_data = extract_chart_data(messages)
        
        if not chart_data and all_charts:
            chart_data = all_charts[0]

        message_content = get_message_content(last_message)

        tool_messages_info = []
        for i, msg in enumerate(messages):
            if type(msg).__name__ == 'ToolMessage':
                content = getattr(msg, 'content', None)
                tool_messages_info.append({
                    "index": i,
                    "name": getattr(msg, 'name', None),
                    "content_type": type(content).__name__,
                    "content_preview": str(content)[:300] if content else None
                })

        debug_info = {
            "messages_count": len(messages),
            "last_message_type": type(last_message).__name__ if last_message else None,
            "has_chart_data": chart_data is not None,
            "all_charts_count": len(all_charts),
            "message_content_preview": message_content[:200] if message_content else None,
            "message_types": [type(m).__name__ for m in messages],
            "tool_messages": tool_messages_info,
            "all_charts": all_charts  # 返回所有图表
        }

        return ApprovalResponse(
            success=True,
            thread_id=request.thread_id,
            message="审核已处理" if request.decision == "approve" else "操作已拒绝",
            result={
                "message": message_content if message_content else None,
                "chart_data": chart_data,
                "all_charts": all_charts,  # 返回所有图表
                "debug_info": debug_info
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{thread_id}", response_model=StateResponse)
async def get_state(thread_id: str):
    """
    获取会话状态

    用于调试和查看执行状态
    可以查看短期记忆中保存的对话历史
    """
    from agent import get_async_agent

    try:
        agent = await get_async_agent()
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
    支持短期记忆（相同 thread_id 保持上下文）
    """
    from agent import get_async_agent

    async def generate() -> AsyncIterator[str]:
        agent = await get_async_agent()
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


@router.get("/checkpoints/stats")
async def get_checkpoint_stats():
    """
    获取 checkpoint 统计信息
    
    返回各表的记录数和日期分布
    """
    from utils.checkpoint_cleanup import get_checkpoint_stats
    return await get_checkpoint_stats()


@router.post("/checkpoints/cleanup")
async def cleanup_checkpoints(
    days_to_keep: int = Query(default=7, ge=1, le=30),
    dry_run: bool = Query(default=True)
):
    """
    清理旧的 checkpoint 数据
    
    参数:
        days_to_keep: 保留最近多少天的数据（默认7天）
        dry_run: 如果为 True，只统计不删除（默认 True）
    
    返回:
        清理结果统计
    """
    from utils.checkpoint_cleanup import cleanup_old_checkpoints
    return await cleanup_old_checkpoints(days_to_keep=days_to_keep, dry_run=dry_run)


@router.post("/checkpoints/cleanup-orphaned")
async def cleanup_orphaned_checkpoints(
    dry_run: bool = Query(default=True)
):
    """
    清理孤立的 checkpoint 数据
    
    参数:
        dry_run: 如果为 True，只统计不删除（默认 True）
    
    返回:
        清理结果统计
    """
    from utils.checkpoint_cleanup import cleanup_orphaned_checkpoints
    return await cleanup_orphaned_checkpoints(dry_run=dry_run)
