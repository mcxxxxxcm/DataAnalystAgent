"""可观测 /metrics（B007）测试：enabled 门控、工具/请求指标、gauge、路由 404。"""

import asyncio
from types import SimpleNamespace

import pytest

from config.settings import get_settings


@pytest.fixture()
def obs_on(monkeypatch):
    """把 observability_enabled 临时打开/关闭。注意指标为模块级累加，测试用唯一名避免互相干扰。"""
    monkeypatch.setattr(get_settings(), "observability_enabled", True)
    yield
    monkeypatch.setattr(get_settings(), "observability_enabled", False)


def _render():
    from observability import metrics as obs
    return obs.render_metrics()


def test_disabled_is_noop():
    # 默认关闭：record 不注册不记录，render 为空
    from observability import metrics as obs
    assert obs.enabled() is False
    obs.record_tool("query_database", 100.0, True)
    obs.record_request("POST", "/api/query", 200, 50.0)
    obs.refresh_pool(1, 1, 2, 1, 0, 4)
    assert _render() == ""


def test_record_tool_emits_counter_and_histogram(obs_on):
    from observability import metrics as obs
    obs.record_tool("unique_q1", 150.0, True)
    obs.record_tool("unique_q1", 60.0, False)
    text = _render()
    assert "agent_tool_calls_total" in text
    assert 'agent_tool_calls_total{tool="unique_q1",outcome="success"} 1' in text
    assert 'agent_tool_calls_total{tool="unique_q1",outcome="error"} 1' in text
    assert "agent_tool_duration_seconds_bucket" in text
    assert "agent_tool_duration_seconds_count 2" in text


def test_record_request_emits_labels(obs_on):
    from observability import metrics as obs
    obs.record_request("POST", "/api/query", 200, 40.0)
    text = _render()
    assert 'http_requests_total{method="POST",path="/api/query",status="200"} 1' in text
    assert "http_request_duration_seconds_count 1" in text


def test_refresh_pool_emits_gauges(obs_on):
    from observability import metrics as obs
    obs.refresh_pool(size=10, min_size=2, max_size=20, idle=3, result_cache_entries=7, thread_pool_size=4)
    text = _render()
    assert 'db_pool_connections{type="size"} 10' in text
    assert 'db_pool_connections{type="max"} 20' in text
    assert "result_cache_entries 7" in text
    assert "tool_thread_pool_size 4" in text


def test_metrics_route_disabled_404(monkeypatch):
    # 关闭时返回 404
    from fastapi import HTTPException
    from api import routes as routes_mod
    monkeypatch.setattr(get_settings(), "observability_enabled", False)
    routes_mod.db_pool = SimpleNamespace(get_stats=lambda: SimpleNamespace(size=1, min_size=1, max_size=2, idle_size=1))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(routes_mod.metrics())
    assert ei.value.status_code == 404


def test_metrics_route_enabled_200(obs_on, monkeypatch):
    from api import routes as routes_mod
    monkeypatch.setattr(get_settings(), "observability_enabled", True)
    routes_mod.db_pool = SimpleNamespace(get_stats=lambda: SimpleNamespace(size=1, min_size=1, max_size=2, idle_size=1))
    from fastapi.responses import PlainTextResponse
    resp = asyncio.run(routes_mod.metrics())
    assert isinstance(resp, PlainTextResponse)
    assert "db_pool_connections" in resp.body.decode()