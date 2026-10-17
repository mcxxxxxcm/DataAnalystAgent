"""
确定性意图路由器

位置：core/security/intent_guard.py
职责：把「用户自然语言查询」在 NL 层分成 意图类别，返回 IntentVerdict，
供评测做「拒答 / 澄清 / 放行」的确定性断言（也作为未来接线到 /query 的判定入口）。

为什么需要它：
- 现有拒答 / 澄清 / 报错全交由 LLM 内部决定，缺少一个可单测、可进 CI 的确定性入口，
  导致「错误案例(非查询 / 模糊 / 越权 / 注入试图)走对路由」这件事无法回归验证。
- 判「有无实体命中」复用 core/database/schema_linking.rank_relevant_tables：
  命中 → 有实体(按词细化 QUERY/CHART/INFO)；兜底 → 无实体(判非数据话题 OUT_OF_SCOPE 或 AMBIGUOUS)。
  复用之，避免另造一套检索(Avoid §4)。

设计约束：全程保守、低误杀。只有「明确」的恶意 / 寒暄 / 无关话题才短路；
一切能映射到表的输入一律放行为 QUERY/CHART/INFO，绝不误伤合法查询。

纯逻辑、无 DB / 无 LLM；table_index 由调用方注入（评测用与 run_eval 一致的合成索引）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.database.schema_linking import rank_relevant_tables  # type: ignore


class Intent(str, Enum):
    """NL 意图类别"""
    QUERY = "query"                      # 数据检索 / 聚合
    CHART = "chart"                      # 要图表
    INFO = "info"                        # 问表结构 / 字段 / 有哪些表
    MALICIOUS = "malicious"              # 恶意 / 越权 / 注入 → 拒绝
    SMALLTALK = "smalltalk"              # 寒暄 → 不执行，礼貌应答
    OUT_OF_SCOPE = "out_of_scope"        # 非数据话题 → 拒绝
    AMBIGUOUS = "ambiguous"              # 太模糊，无实体 → 澄清


@dataclass
class IntentVerdict:
    """意图判定结果。deny=True 表示不应继续到 Agent/SQL；clarify=True 表示应追问澄清。"""
    category: Intent
    reason: str
    deny: bool = False
    clarify: bool = False
    reply: Optional[str] = None

    def __post_init__(self) -> None:
        # 类别与布尔语义一致性兜底：这些类别天然「不放行」。
        if self.category in (Intent.MALICIOUS, Intent.OUT_OF_SCOPE):
            self.deny = True
        if self.category == Intent.SMALLTALK:
            self.deny = True
            self.reply = self.reply or "你好，我是数据分析助手，请问你想查哪些数据？"

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "deny": self.deny,
            "clarify": self.clarify,
            "reason": self.reason,
            "reply": self.reply,
        }


# ── 判定用正则(保守,低误杀) ──────────────────────────────
# SQL 式危险意图
_SQL_DESTRUCTIVE = re.compile(
    r"\b(drop\s+table|drop\s+database|delete\s+from|truncate\s+(table|database)"
    r"|create\s+table|alter\s+table|update\s+\w+\s+set)\b",
    re.IGNORECASE,
)
# 注入特征(堆叠语句 / 恒真 / 注释)
_INJECTION = re.compile(
    r";\s*(drop|delete|update|insert|truncate|grant)"
    r"|or\s+'1'\s*=\s*'1'|or\s+1\s*=\s*1\b"
    r"|union\s+select\b|--;|/\*",
    re.IGNORECASE,
)
# 中文破坏意图
_CN_DESTRUCTIVE = re.compile(
    r"(删库|删掉|删除.*(表|库|数据)|清空.*(表|库|数)|清掉.*(表|库)"
    r"|全部.*删|把.*删|初始化.*(表|库)|还原.*(表|库)|换库里所有.*(表|数据))"
)
# 越权 / 绕过审批
_BYPASS = re.compile(
    r"(绕过|不经过|取消.*(审批|审核|确认)|跳过.*(审批|审核)"
    r"|别记录|不要记录|不写日志|偷偷|后台.*(改|删)|直接把.*改|强制.*改)"
)
# 寒暄
_SMALLTALK = re.compile(
    r"^(你好|您好|hi|hello|嗨|哈喽|在吗|在不在|谢谢|辛苦了|感谢|感谢你"
    r"|你是谁|你会什么|你能做什么|介绍一下自己|早上好|晚上好|你好呀|在么)"
)
# 非数据话题(与任何表无关)
_NON_DATA = re.compile(
    r"(写.*(诗|歌|文章|文案|代码)|推荐.*(电影|音乐|书|餐厅)|讲个笑话"
    r"|今天天气|唱首歌|做.*(饭|菜)|菜谱|帮我算命|你是人吗)"
)
# 图表词 → CHART
_CHART_WORDS = re.compile(r"(图|图表|柱状|折线|饼|趋势|可视化|画图|柱形|走势图|占比)")
# 结构/元信息词 → INFO
_INFO_WORDS = re.compile(r"(结构|字段|列名|有哪些表|有哪些列|表名|含义|定义|建表|长什么样)")


def classify_intent(
    text: str,
    table_index,
    max_candidates: int = 2,
    allow_smalltalk: bool = True,
    user_patterns: Optional[dict] = None,
) -> IntentVerdict:
    """
    对用户 NL 做确定性意图分类。

    参数:
        text: 用户输入(自然语言)。
        table_index: 已被 SchemaManager 注入好同义词的 TableIndex(评测用合成索引)。
        max_candidates: 实体命中判定的候选表上限,取小即可。
        allow_smalltalk: 是否启用寒暄识别(可关掉,便于仅测业务分类)。
        user_patterns: 可选覆盖,支持 key 'destructive'/'bypass'/'non_data' 的正则追加(默认空)。

    返回:
        IntentVerdict。deny=True 时调用方不应继续到 Agent/SQL。
    """
    text = (text or "").strip()
    if not text:
        return IntentVerdict(Intent.AMBIGUOUS, "输入为空，需要澄清具体查询", clarify=True)

    low = text.lower()

    # 1) 恶意：注入 / 危险 SQL / 中文破坏 / 越权
    if _INJECTION.search(low) or _SQL_DESTRUCTIVE.search(low):
        return IntentVerdict(Intent.MALICIOUS, f"检测到注入/危险 SQL 特征：{text[:40]}")
    if _CN_DESTRUCTIVE.search(text) or _BYPASS.search(text):
        return IntentVerdict(Intent.MALICIOUS, f"检测到破坏/越权意图：{text[:40]}")
    if user_patterns:
        _u_dest = user_patterns.get("destructive") or ""
        _u_bypass = user_patterns.get("bypass") or ""
        if (_u_dest and re.search(_u_dest, text)) or (_u_bypass and re.search(_u_bypass, text)):
            return IntentVerdict(Intent.MALICIOUS, f"命中用户自定义恶意/越权规则：{text[:40]}")

    # 2) 寒暄(可选)
    if allow_smalltalk and _SMALLTALK.match(low):
        return IntentVerdict(Intent.SMALLTALK, "寒暄，不执行查询，礼貌引导")

    # 3) 实体命中判定：复用 schema_linking 的加权检索(不带 priority/recent,避免假命中)
    ranked = rank_relevant_tables(text, table_index, max_tables=max_candidates)
    if ranked and ranked[0].score > 0:
        top = ranked[0].table
        if _CHART_WORDS.search(text):
            return IntentVerdict(Intent.CHART, f"命中表 {top} 且带图表意图：{text[:40]}")
        if _INFO_WORDS.search(text):
            return IntentVerdict(Intent.INFO, f"命中表 {top} 且问结构/元信息：{text[:40]}")
        return IntentVerdict(Intent.QUERY, f"命中表 {top}：{text[:40]}")

    # 4) 无实体命中 → 非数据话题 或 歧义
    if _NON_DATA.search(text) or (user_patterns or {}).get("non_data") and re.search(
        (user_patterns or {}).get("non_data", ""), text
    ):
        return IntentVerdict(Intent.OUT_OF_SCOPE, f"与数据无关的话题：{text[:40]}")
    return IntentVerdict(
        Intent.AMBIGUOUS,
        f"无法确定要查询哪张表/哪个指标，需澄清：{text[:40]}",
        clarify=True,
    )