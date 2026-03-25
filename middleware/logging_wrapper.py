"""
日志中间件包装器

简化版本：直接记录日志，不使用 wrap_tool_call
"""

import time
from typing import Callable, Any, Dict, Optional

from .logging_middleware import local_logger


class LoggingMiddleware:
    """
    日志中间件类
    
    记录工具调用的输入输出和执行时间
    """
    
    def __init__(self):
        self.enabled = True
    
    def wrap_tool(self, tool_func: Callable) -> Callable:
        """
        包装工具函数，添加日志记录
        
        参数:
            tool_func: 原始工具函数
            
        返回:
            包装后的函数
        """
        def wrapper(*args, **kwargs) -> Any:
            if not self.enabled:
                return tool_func(*args, **kwargs)
            
            tool_name = getattr(tool_func, '__name__', 'unknown')
            start_time = time.time()
            
            try:
                result = tool_func(*args, **kwargs)
                
                execution_time_ms = (time.time() - start_time) * 1000
                local_logger.log_tool_call(
                    thread_id=kwargs.get('thread_id', 'unknown'),
                    tool_name=tool_name,
                    input_args=kwargs,
                    output=str(result)[:2000] if result else None,
                    success=True,
                    execution_time_ms=execution_time_ms
                )
                
                return result
                
            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                local_logger.log_tool_call(
                    thread_id=kwargs.get('thread_id', 'unknown'),
                    tool_name=tool_name,
                    input_args=kwargs,
                    success=False,
                    execution_time_ms=execution_time_ms,
                    error=str(e)
                )
                raise
        
        return wrapper
    
    async def wrap_tool_async(self, tool_func: Callable) -> Callable:
        """
        包装异步工具函数
        """
        async def wrapper(*args, **kwargs) -> Any:
            if not self.enabled:
                return await tool_func(*args, **kwargs)
            
            tool_name = getattr(tool_func, '__name__', 'unknown')
            start_time = time.time()
            
            try:
                result = await tool_func(*args, **kwargs)
                
                execution_time_ms = (time.time() - start_time) * 1000
                local_logger.log_tool_call(
                    thread_id=kwargs.get('thread_id', 'unknown'),
                    tool_name=tool_name,
                    input_args=kwargs,
                    output=str(result)[:2000] if result else None,
                    success=True,
                    execution_time_ms=execution_time_ms
                )
                
                return result
                
            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                local_logger.log_tool_call(
                    thread_id=kwargs.get('thread_id', 'unknown'),
                    tool_name=tool_name,
                    input_args=kwargs,
                    success=False,
                    execution_time_ms=execution_time_ms,
                    error=str(e)
                )
                raise
        
        return wrapper


def create_logging_middleware() -> LoggingMiddleware:
    """创建日志中间件实例"""
    return LoggingMiddleware()


logging_middleware = create_logging_middleware()