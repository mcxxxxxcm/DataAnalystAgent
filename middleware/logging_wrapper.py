"""
日志中间件

使用 @wrap_tool_call 装饰器记录工具调用（异步版本）
"""

import time
from typing import Any

from langchain.agents.middleware import wrap_tool_call

from .logging_middleware import local_logger


@wrap_tool_call
async def logging_middleware(request, handler) -> Any:
    """
    日志中间件 - 记录工具调用的输入输出和执行时间（异步版本）
    
    参数:
        request: 工具调用请求
        handler: 执行工具的处理器
        
    返回:
        工具执行结果
    """
    tool_name = getattr(request, 'name', 'unknown')
    tool_args = getattr(request, 'args', {})
    
    start_time = time.time()
    
    try:
        result = await handler(request)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        local_logger.log_tool_call(
            thread_id='current',
            tool_name=tool_name,
            input_args=tool_args,
            output=str(result)[:2000] if result else None,
            success=True,
            execution_time_ms=execution_time_ms
        )
        
        return result
        
    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        
        local_logger.log_tool_call(
            thread_id='current',
            tool_name=tool_name,
            input_args=tool_args,
            success=False,
            execution_time_ms=execution_time_ms,
            error=str(e)
        )
        raise
