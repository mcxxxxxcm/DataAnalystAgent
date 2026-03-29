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

CHART_TOOL_NAMES = {
    'create_line_chart', 'create_bar_chart', 'create_pie_chart',
    'create_chart', 'create_custom_chart'
}


def format_approval_request(interrupt_data: List[Any], thread_id: str) -> Dict[str, Any]:
    """
    格式化审核请求，使其更友好
    
    Args:
        interrupt_data: 原始中断数据（可能是 Interrupt 对象或字典）
        thread_id: 会话ID
        
    Returns:
        格式化后的审核请求
    """
    from api.schemas import FormattedApprovalRequest, ActionRequest
    
    actions = []
    
    for item in interrupt_data:
        # 处理 Interrupt 对象
        if hasattr(item, 'value'):
            value = item.value
        elif isinstance(item, dict):
            value = item.get("value", {})
        else:
            continue
        
        # 获取 action_requests
        if isinstance(value, dict):
            action_requests = value.get("action_requests", [])
        elif hasattr(value, 'get'):
            action_requests = value.get("action_requests", [])
        else:
            action_requests = []
        
        for action in action_requests:
            if isinstance(action, dict):
                tool_name = action.get("name", "unknown")
                args = action.get("args", {})
                description = action.get("description", "")
            elif hasattr(action, 'name'):
                tool_name = action.name
                args = getattr(action, 'args', {})
                description = getattr(action, 'description', '')
            else:
                continue
            
            # 判断风险等级
            risk_level = "low"
            if tool_name == "query_database":
                sql = args.get("query", "").upper() if isinstance(args, dict) else ""
                if "DELETE" in sql or "DROP" in sql or "TRUNCATE" in sql:
                    risk_level = "high"
                elif "UPDATE" in sql or "INSERT" in sql:
                    risk_level = "medium"
            
            # 生成友好的描述
            friendly_desc = _generate_friendly_description(tool_name, args, description)
            
            actions.append(ActionRequest(
                tool_name=tool_name,
                description=friendly_desc,
                sql=args.get("query") if isinstance(args, dict) and tool_name == "query_database" else None,
                risk_level=risk_level
            ))
    
    # 生成标题和消息
    if len(actions) == 1:
        title = f"⚠️ 需要审核: {actions[0].tool_name}"
        message = f"此操作需要人工确认后才能执行。"
    else:
        title = f"⚠️ 需要审核: {len(actions)} 个操作"
        message = "以下操作需要人工确认后才能执行。"
    
    return FormattedApprovalRequest(
        title=title,
        message=message,
        actions=actions,
        allowed_decisions=["approve", "reject"],
        thread_id=thread_id
    )


def _generate_friendly_description(tool_name: str, args: Dict, original_desc: str) -> str:
    """生成友好的操作描述"""
    if tool_name == "query_database":
        sql = args.get("query", "")
        sql_upper = sql.upper().strip()
        
        if sql_upper.startswith("SELECT"):
            return f"📊 查询数据\n执行 SELECT 查询，读取数据。"
        elif sql_upper.startswith("INSERT"):
            return f"➕ 插入数据\n将向数据库插入新记录。"
        elif sql_upper.startswith("UPDATE"):
            return f"✏️ 更新数据\n将修改数据库中的现有记录。"
        elif sql_upper.startswith("DELETE"):
            return f"🗑️ 删除数据\n将从数据库删除记录（不可恢复）。"
        else:
            return f"🔧 执行 SQL\n{sql[:100]}..."
    
    elif tool_name == "create_chart":
        chart_type = args.get("chart_type", "unknown")
        return f"📈 生成图表\n创建 {chart_type} 类型图表。"
    
    else:
        return original_desc[:200] if original_desc else f"执行 {tool_name}"


def extract_chart_data(messages: List[Any]) -> Optional[Dict[str, Any]]:
    """
    从消息列表中提取图表数据
    
    Args:
        messages: Agent 返回的消息列表
        
    Returns:
        图表数据字典或 None
    """
    from tools.chart_tools import get_cached_chart
    
    for msg in reversed(messages):
        msg_type = type(msg).__name__
        
        if msg_type == 'ToolMessage':
            try:
                content = getattr(msg, 'content', '{}')
                if isinstance(content, str):
                    tool_result = json.loads(content)
                else:
                    tool_result = content if isinstance(content, dict) else {}
                
                image_base64 = tool_result.get('image_base64', '')
                if image_base64:
                    # 处理 chart_id 格式
                    if image_base64.startswith('chart_id:'):
                        chart_id = image_base64.split(':')[1]
                        actual_image = get_cached_chart(chart_id)
                        if actual_image:
                            tool_result['image_base64'] = actual_image
                        else:
                            continue
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
                
                image_base64 = tool_result.get('image_base64', '')
                if image_base64:
                    # 处理 chart_id 格式
                    if image_base64.startswith('chart_id:'):
                        chart_id = image_base64.split(':')[1]
                        actual_image = get_cached_chart(chart_id)
                        if actual_image:
                            tool_result['image_base64'] = actual_image
                        else:
                            continue
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
    from tools.chart_tools import get_cached_chart
    
    charts = []
    seen_chart_ids = set()
    
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        msg_name = getattr(msg, 'name', None)
        
        if msg_type == 'ToolMessage':
            content = getattr(msg, 'content', None)
            
            if isinstance(content, str):
                try:
                    tool_result = json.loads(content)
                    if isinstance(tool_result, dict) and tool_result.get('image_base64'):
                        chart_type = tool_result.get('chart_type', 'unknown')
                        message = tool_result.get('message', '')
                        image_base64 = tool_result.get('image_base64', '')
                        
                        # 处理 chart_id 格式
                        if image_base64.startswith('chart_id:'):
                            chart_id_key = image_base64.split(':')[1]
                            actual_image = get_cached_chart(chart_id_key)
                            if actual_image:
                                tool_result['image_base64'] = actual_image
                                image_base64 = actual_image
                            else:
                                continue
                        
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
            formatted_request = format_approval_request(interrupt_data, thread_id)
            return QueryResponse(
                success=False,
                thread_id=thread_id,
                requires_approval=True,
                approval_request=formatted_request,
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
