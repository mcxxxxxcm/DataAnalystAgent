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

    模型视图可重建不变量（M1）：记录真实 thread_id 与 model_view，
    使「发给模型的完整消息序列」可由会话日志重建（Model-visible ⟺ logged）。

    参数:
        request: 工具调用请求（含 runtime.config 可解析 thread_id）
        handler: 执行工具的处理器

    返回:
        工具执行结果
    """
    tool_name = getattr(request, 'name', 'unknown')
    tool_args = getattr(request, 'args', {})

    thread_id = _resolve_thread_id(request)

    start_time = time.time()

    try:
        result = await handler(request)

        execution_time_ms = (time.time() - start_time) * 1000

        local_logger.log_tool_call(
            thread_id=thread_id,
            tool_name=tool_name,
            input_args=tool_args,
            output=str(result)[:2000] if result else None,
            success=True,
            execution_time_ms=execution_time_ms,
            model_view=_capture_model_view(result),
        )

        return result

    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000

        local_logger.log_tool_call(
            thread_id=thread_id,
            tool_name=tool_name,
            input_args=tool_args,
            success=False,
            execution_time_ms=execution_time_ms,
            error=str(e),
            model_view=_capture_model_view(None),
        )
        raise


def _resolve_thread_id(request: Any) -> str:
    """从 ToolCallRequest.runtime.config 解析真实 thread_id，缺失回退 'current'。"""
    try:
        runtime = getattr(request, 'runtime', None) or {}
        config = getattr(runtime, 'config', None)
        tid = (config or {}).get("configurable", {}).get("thread_id")
        return tid if tid else 'current'
    except Exception:
        return 'current'


def _capture_model_view(result: Any) -> Any:
    """
    捕获模型视图内容：与送入 LLM 的裁剪同一阈值对 result 做 condense。

    开关由 settings.recon_model_view_enabled 控制（默认开）；关闭时返回 None。
    """
    from config.settings import get_settings
    from middleware.truncation import condense_tool_result, truncation_settings

    if not get_settings().recon_model_view_enabled:
        return None

    try:
        s = truncation_settings()
        return condense_tool_result(
            str(result) if result is not None else None,
            max_rows=s["max_rows"],
            max_chars_per_cell=s["max_chars_per_cell"],
            max_content_len=s["max_content_len"],
        )
    except Exception:
        return None