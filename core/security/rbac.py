"""
表/列级 RBAC（最小授权，backlog B010）

位置：core/security/rbac.py
职责：
- 定义角色策略（RolePolicy / Policy），并从 JSON（字面量或 @文件路径）加载。
- 由请求来源 key 解析角色（resolve_role）。
- 生成「表 + 列」组合守卫供 query_database 注入 guard_query_sql（additive，不替换系统白名单）。

安全约定：
- 默认关闭（enable_rbac=False）。关闭时 build_role_guards 返回 (None, None)，守卫路径零改动。
- 列级采用 sqlparse 从 SQL 提取该表引用列；解析失败 / SELECT * → fail-closed 拒绝（宁可多拒）。
- enable_rbac=True 且来源无法解析到任何角色时，入口层拒绝（防未授权来源走宽松默认）。
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set

# 当前请求角色（在 /query 入口 set，工具内读取以决定是否注入 RBAC 守卫）。
# 单 asyncio task 内传播给后续工具调用（同一 loop），跨请求隔离。
current_role: ContextVar[Optional[str]] = ContextVar("rbac_current_role", default=None)


@dataclass
class RolePolicy:
    """一个角色的最小授权。tables=set 时限制可访问表；columns=表→允许列集合。"""
    tables: Optional[Set[str]] = None
    columns: Dict[str, Set[str]] = field(default_factory=dict)
    tools_scope: str = "full"


@dataclass
class Policy:
    """整份 RBAC 策略。default_role 供未列出的来源回退；None 表示未匹配即拒绝。"""
    roles: Dict[str, RolePolicy]
    default_role: Optional[str] = None

    @classmethod
    def from_json(cls, text: str) -> "Policy":
        """从 JSON 字面量或 '@相对路径' 加载。格式：
        {"default_role": "viewer", "roles": {"viewer": {"tables": ["sales"], "columns": {"sales": ["a","b"]}, "tools_scope": "read_only"}}}
        """
        if not text or not str(text).strip():
            return cls(roles={})
        payload = str(text).strip()
        if payload.startswith("@"):
            path = Path(payload[1:])
            if not path.is_absolute():
                from config.settings import PROJECT_ROOT
                path = PROJECT_ROOT / path
            payload = path.read_text(encoding="utf-8")
        data = json.loads(payload)
        roles: Dict[str, RolePolicy] = {}
        for name, spec in (data.get("roles") or {}).items():
            roles[name.lower()] = RolePolicy(
                tables=set(spec["tables"]) if spec.get("tables") else None,
                columns={str(k).lower(): set(v) for k, v in (spec.get("columns") or {}).items()},
                tools_scope=spec.get("tools_scope", "full"),
            )
        return cls(roles=roles, default_role=(data.get("default_role") or "").lower() or None)

    def resolve_role(self, source: Optional[str]) -> Optional[str]:
        """来源 key → 角色；未命中回退 default_role；无 default 返回 None（应由入口拒绝）。"""
        if source:
            r = source.strip().lower()
            if r in self.roles:
                return r
        return self.default_role


# 策略单例（lazy）。由 config.settings.rbac_policy_json 初始化；enable_rbac=False 时无需加载。
_policy: Optional[Policy] = None
_policy_loaded = False


def get_policy() -> Optional[Policy]:
    """加载并缓存策略（lazy）。不配置 rbac_policy_json 时返回空策略（无任何角色）。"""
    global _policy, _policy_loaded
    if not _policy_loaded:
        from config.settings import get_settings
        _policy = Policy.from_json(get_settings().rbac_policy_json)
        _policy_loaded = True
    return _policy


def resolve_role(source: Optional[str]) -> Optional[str]:
    """由请求来源解析当前请求角色（仅供入口用；工具层读 current_role contextvar）。"""
    return get_policy().resolve_role(source)


# ---- 列级提取（sqlparse, fail-closed）----
def _select_clause(sql: str) -> Optional[str]:
    """提取 SELECT 到第一个 FROM 之间的列片段文本。"""
    m = re.match(r"^\s*SELECT\s+(?P<cols>.*?)\s+FROM\b", str(sql), re.I | re.S)
    return m.group("cols") if m else None


def _table_in_sql(sql: str, table: str) -> bool:
    return bool(
        re.search(r"\bFROM\s+\b" + re.escape(table) + r"\b", sql, re.I)
        or re.search(r"\bJOIN\s+\b" + re.escape(table) + r"\b", sql, re.I)
    )


def extract_columns(sql: str, table: str) -> Optional[Set[str]]:
    """
    提取 SQL 中对目标表的显式列引用。未涉及该表 → None（无需校验）。
    解析失败或 `*` → 抛 ValueError（fail-closed，拒绝）。
    """
    if not _table_in_sql(str(sql), table):
        return None
    sel = _select_clause(str(sql))
    if sel is None:
        raise ValueError("无法定位 SELECT 列，拒绝访问")
    if re.search(r"(^|,)\s*(\w+\.\*|\*)", sel):
        raise ValueError(f"不允许对受列级保护的表 {table} 使用 SELECT *")
    cols: Set[str] = set()
    for part in sel.split(","):
        part = re.sub(r"\s+(AS|as)\s+.*$", "", part).strip()
        if not part:
            continue
        if table + "." in part:
            name = part.split(table + ".")[-1].split()[0].strip()
            if name:
                cols.add(name)
        # 裸列无法可靠归属，不纳入列级校验（仍受表级 + 系统边界约束）
    return cols


def build_role_guards(policy: Optional[Policy], role: Optional[str]):
    """
    生成该角色的 (table_checker, column_checker)，供 guard_query_sql 注入。
    角色/策略缺失或关闭 → (None, None)，守卫路径保持现状（仅系统白名单）。
    table_checker 组合「先 is_allowed_table（系统表/存在性）→ 角色表白名单」（additive 非替换）。
    """
    if policy is None or role is None:
        return (None, None)
    rp = policy.roles.get(role)
    if rp is None:
        return (None, None)

    from tools.boundaries import is_allowed_table

    async def table_checker(table: str) -> None:
        await is_allowed_table(table)
        if rp.tables is not None and table not in rp.tables:
            raise ValueError(f"角色 {role} 无权访问表 {table}")

    column_checker = None
    if rp.columns:
        async def column_checker(sql: str) -> None:
            for tbl, allowed in rp.columns.items():
                cols = extract_columns(sql, tbl)
                if cols is None:
                    continue
                denied = sorted(cols - allowed)
                if denied:
                    raise ValueError(f"角色 {role} 无权限访问表 {tbl} 的列: {', '.join(denied)}")
    return (table_checker, column_checker)