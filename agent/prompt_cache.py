"""
提示词缓存工具（backlog B005）

位置：agent/prompt_cache.py
职责：
- 标记「固定系统段 / 本轮动态段」分界，让固定前缀稳定置顶以命中支持自动磁盘缓存的 provider，
  减少相同提示词每轮的重复计费 token。
- 可选注入显式 cache 头（如兼容 Anthropic cache_control 风格的 provider），默认不注入。

关闭/未配置时所有逻辑返回 None / 原样，不改变提示词内容与调用方行为。
"""

from __future__ import annotations

import json
from typing import Optional, Tuple

# 固定段与动态段的分界标记。仅当 prompt_cache_enabled=True 时才插入固定段尾。
_MARKER = "\n\n## —— 本轮动态部分（随会话变化，不参与稳定缓存）——\n\n"


def _build_prompt_with_marker(system_prompt: str = "", db_info: str = "", custom_instructions: str = "") -> str:
    """按「固定段 + marker + 动态段」拼装（prompt_cache_enabled=True 路径）。"""
    prompt = system_prompt + _MARKER
    if db_info:
        prompt += f"\n\n## 数据库信息\n\n{db_info}"
    if custom_instructions:
        prompt += f"\n\n## 特殊指令\n\n{custom_instructions}"
    return prompt


def split_cached_prompt(prompt: str) -> Optional[Tuple[str, str]]:
    """
    按 marker 把提示词切成 (固定段, 动态段)。无 marker 返回 None（表示未启用缓存布局）。
    """
    if not prompt or _MARKER not in prompt:
        return None
    fixed, _, dynamic = prompt.partition(_MARKER)
    return (fixed, dynamic)


def build_cache_kwargs(prompt: str, header_json: str) -> Optional[dict]:
    """
    解析显式 cache 头 JSON 字面量为待注入的 dict（如 anthropic 风格的 cache_control）。
    空/非法/非 dict 返回 None（调用方不注入）。固定段为空时也无谓注入 → None。
    """
    if not header_json or not str(header_json).strip():
        return None
    try:
        header = json.loads(str(header_json))
    except (ValueError, TypeError):
        return None
    if not isinstance(header, dict) or not header:
        return None
    return header