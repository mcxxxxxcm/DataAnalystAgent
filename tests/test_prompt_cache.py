"""提示词缓存（B005）测试：off 逐字节不变、on 动态段置尾、切分、cache 头注入。"""

from agent.prompt_cache import _MARKER, build_cache_kwargs, split_cached_prompt
from agent.prompts import SYSTEM_PROMPT, build_system_prompt
from config.settings import get_settings


def _settings_to(monkeypatch, **kw):
    s = get_settings()
    for k, v in kw.items():
        monkeypatch.setattr(s, k, v)


def test_off_byte_identical(monkeypatch):
    # 默认/prompt_cache_enabled=False：输出与既有拼接逐字节一致
    _settings_to(monkeypatch, prompt_cache_enabled=False)
    p = build_system_prompt(db_info="数据库: analytics", custom_instructions="请用中文回复用户")
    expect = SYSTEM_PROMPT
    expect += "\n\n## 数据库信息\n\n数据库: analytics"
    expect += "\n\n## 特殊指令\n\n请用中文回复用户"
    assert p == expect
    assert _MARKER not in p


def test_off_no_extra_when_empty(monkeypatch):
    _settings_to(monkeypatch, prompt_cache_enabled=False)
    p = build_system_prompt()
    assert p == SYSTEM_PROMPT


def test_on_marks_and_dynamic_tail(monkeypatch):
    _settings_to(monkeypatch, prompt_cache_enabled=True)
    p = build_system_prompt(db_info="数据库: analytics", custom_instructions="请用中文回复用户")
    # 固定段 = SYSTEM_PROMPT，marker 后为动态段
    fixed, dynamic = split_cached_prompt(p)
    assert fixed == SYSTEM_PROMPT
    assert _MARKER in p
    assert "数据库: analytics" in dynamic and "请用中文回复用户" in dynamic


def test_on_empty_dynamic_marker_added(monkeypatch):
    # 无动态段时也保留 marker（固定前缀边界稳定），动态部分为空串
    _settings_to(monkeypatch, prompt_cache_enabled=True)
    p = build_system_prompt()
    assert p == SYSTEM_PROMPT + _MARKER
    fixed, dynamic = split_cached_prompt(p)
    assert fixed == SYSTEM_PROMPT and dynamic == ""


def test_split_cached_prompt_pairs():
    fixed, dynamic = split_cached_prompt(SYSTEM_PROMPT + _MARKER + "## 动态")
    assert fixed == SYSTEM_PROMPT
    assert dynamic == "## 动态"
    assert split_cached_prompt("no marker") is None


def test_build_cache_kwargs_variants():
    valid = '{"cache_control": {"type": "ephemeral"}}'
    assert build_cache_kwargs("p", valid) == {"cache_control": {"type": "ephemeral"}}
    assert build_cache_kwargs("p", "") is None
    assert build_cache_kwargs("p", "not json{") is None
    assert build_cache_kwargs("p", "[]") is None   # 非 dict
    assert build_cache_kwargs("p", "{}") is None   # 空 dict
    assert build_cache_kwargs("p", None) is None


def test_llm_cache_kwargs_gate(monkeypatch):
    # 关：_llm_cache_model_kwargs 返回 None（不注入）；开 + 合法 header → 注入 extra_body
    from agent.analyst_agent import _llm_cache_model_kwargs
    _settings_to(monkeypatch, prompt_cache_enabled=False, prompt_cache_header_json='{"x":1}')
    assert _llm_cache_model_kwargs("p") is None
    _settings_to(monkeypatch, prompt_cache_enabled=True, prompt_cache_header_json='{"cache_control": {"type": "ephemeral"}}')
    got = _llm_cache_model_kwargs(SYSTEM_PROMPT)
    assert got is not None
    assert got["model_kwargs"]["extra_body"]["cache_control"]["type"] == "ephemeral"
    # 开但 header 非法 → 不注入
    _settings_to(monkeypatch, prompt_cache_enabled=True, prompt_cache_header_json="bad[")
    assert _llm_cache_model_kwargs("p") is None