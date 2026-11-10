"""
轻量 Prometheus 文本指标。
- 零外部依赖（纯标准库），避免为一个小端点引入包，天然满足本仓「可选/降级」约束。
- 格式与 Prometheus text exposition 兼容，可直接被 `/metrics` 消费或接 OTel prometheus 导出器。
- 所有 record_* 在 `enabled()` 为假时即 no-op，不给业务加开销。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Tuple

from config.settings import get_settings


def enabled() -> bool:
    """是否启用可观测指标（config.observability_enabled）。关闭时所有采集为 no-op。"""
    return bool(get_settings().observability_enabled)


# 指标注册表：name -> dict(type, help, label_names, values/buckets...)
_METRICS: Dict[str, Dict] = {}
_LOCK = threading.Lock()


def _register(name: str, type_: str, help: str, label_names: Tuple[str, ...]) -> Dict:
    with _LOCK:
        m = _METRICS.setdefault(name, {"type": type_, "help": help, "label_names": label_names, "values": {}})
        if type_ == "histogram":
            m.setdefault("buckets", [0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
            m.setdefault("buckets_map", {})
            m.setdefault("sum", 0.0)
            m.setdefault("count", 0)
    return m


# ---- 工具指标（复用 logging_wrapper 埋点点位）----
_tool_total = None
_tool_hist = None


def _ensure_tool_metrics() -> None:
    global _tool_total, _tool_hist
    if _tool_total is None:
        _tool_total = _register("agent_tool_calls_total", "counter", "工具调用次数（按工具/结果）", ("tool", "outcome"))
        _tool_hist = _register("agent_tool_duration_seconds", "histogram", "工具执行耗时（秒）", ())


def record_tool(tool_name: str, ms: float, success: bool) -> None:
    """记录一次工具调用：计数（成功/失败）+ 耗时直方图。关闭时 no-op。"""
    if not enabled():
        return
    _ensure_tool_metrics()
    _inc(_tool_total, (str(tool_name or "unknown"), "success" if success else "error"))
    _observe(_tool_hist, ms / 1000.0)


# ---- 请求指标（api/main 中间件）----
_http_total = None
_http_hist = None


def _ensure_http_metrics() -> None:
    global _http_total, _http_hist
    if _http_total is None:
        _http_total = _register("http_requests_total", "counter", "HTTP 请求（按 method/path/status）", ("method", "path", "status"))
        _http_hist = _register("http_request_duration_seconds", "histogram", "HTTP 请求处理耗时（秒）", ())


def record_request(method: str, path: str, status: int, ms: float) -> None:
    if not enabled():
        return
    _ensure_http_metrics()
    _inc(_http_total, (str(method), str(path), str(status)))
    _observe(_http_hist, ms / 1000.0)


# ---- 系统 gauge（复用 /stats 数据）----
_pool_gauge = None
_result_gauge = None
_thread_gauge = None


def _ensure_system_gauges() -> None:
    global _pool_gauge, _result_gauge, _thread_gauge
    if _pool_gauge is None:
        _pool_gauge = _register("db_pool_connections", "gauge", "数据库连接池连接数", ("type",))
        _result_gauge = _register("result_cache_entries", "gauge", "结果缓存条目数", ())
        _thread_gauge = _register("tool_thread_pool_size", "gauge", "工具线程池 worker 数", ())


def refresh_pool(size: int, min_size: int, max_size: int, idle: int, result_cache_entries: int, thread_pool_size: int) -> None:
    """依据 /stats 的快照刷新连接池等 gauge。关闭时 no-op。"""
    if not enabled():
        return
    _ensure_system_gauges()
    for label, value in (("size", size), ("min", min_size), ("max", max_size), ("idle", idle)):
        _set(_pool_gauge, (label,), float(value))
    _set(_result_gauge, (), float(result_cache_entries))
    _set(_thread_gauge, (), float(thread_pool_size))


# ---- 累加原语 ----
def _inc(metric: Dict, label_values: Tuple[str, ...]) -> None:
    with _LOCK:
        metric["values"][label_values] = metric["values"].get(label_values, 0) + 1


def _set(metric: Dict, label_values: Tuple[str, ...], value: float) -> None:
    with _LOCK:
        metric["values"][label_values] = value


def _observe(hist: Dict, value: float) -> None:
    with _LOCK:
        for b in hist["buckets"]:
            if value <= b:
                hist["buckets_map"][b] = hist["buckets_map"].get(b, 0) + 1
        hist["sum"] += value
        hist["count"] += 1


# ---- 渲染 ----
def _escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(label_names: Tuple[str, ...], values: Tuple[Any, ...]) -> str:
    if not label_names:
        return ""
    inner = ",".join(f'{n}="{_escape(v)}"' for n, v in zip(label_names, values))
    return "{" + inner + "}"


def render_metrics() -> str:
    """生成 Prometheus 文本格式。"""
    lines: List[str] = []
    with _LOCK:
        items = [(name, dict(m)) for name, m in _METRICS.items() if (m.get("values") or (m.get("type") == "histogram" and m.get("count", 0) > 0))]
    for name, m in items:
        lines.append(f"# HELP {name} {m['help']}")
        lines.append(f"# TYPE {name} {m['type']}")
        if m["type"] == "histogram":
            for bucket, count in sorted(m.get("buckets_map", {}).items()):
                lines.append(f"{name}_bucket{{le=\"{bucket}\"}} {count}")
            lines.append(f"{name}_bucket{{le=\"+Inf\"}} {m['count']}")
            lines.append(f"{name}_sum {m['sum']:.6f}")
            lines.append(f"{name}_count {m['count']}")
        else:
            label_names = m["label_names"]
            for lv, val in m["values"].items():
                lines.append(f"{name}{_labels(label_names, lv)} {val}")
    return "\n".join(lines) + "\n" if lines else ""