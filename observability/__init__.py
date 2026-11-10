"""应用可观测性初始化入口。

提供 `enabled()` 决定是否采集/暴露指标；`setup_observability()` 在启用时初始化（当前为宽松 no-op）。
所有采集函数在关闭时均为 no-op，避免任何性能与逻辑影响。
"""

from __future__ import annotations

from config.settings import get_settings

from . import metrics as _metrics


def enabled() -> bool:
    """是否启用可观测指标（config.observability_enabled）。"""
    return bool(get_settings().observability_enabled)


def setup_observability() -> None:
    """启动时初始化（如需可在此接入 tracing 等）。当前仅记录状态。"""
    if enabled():
        print("[observability] 可观测指标已启用（/api/metrics）")


__all__ = ["enabled", "setup_observability", "metrics"]