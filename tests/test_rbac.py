"""表/列级 RBAC（B010）测试：策略解析、角色解析、列提取、组合守卫 additive。"""

import asyncio
import json

import pytest

import tools.boundaries as boundaries
from core.security.rbac import (
    Policy,
    build_role_guards,
    current_role,
    extract_columns,
)

# 样本策略：viewer 只能访问 sales 里 a/b 两列；sensitive 表 physical 完全不可见
_SAMPLE = {
    "default_role": "viewer",
    "roles": {
        "viewer": {
            "tables": ["sales"],
            "columns": {"sales": ["a", "b"]},
            "tools_scope": "read_only",
        },
        "admin": {"tables": None, "tools_scope": "full"},
    },
}


@pytest.fixture()
def policy():
    return Policy.from_json(json.dumps(_SAMPLE))


# ---- 策略 / 角色解析 ----
def test_from_json_parses(policy):
    assert list(policy.roles.keys()) == ["viewer", "admin"]
    assert policy.roles["viewer"].tables == {"sales"}
    assert policy.roles["viewer"].columns == {"sales": {"a", "b"}}
    assert policy.default_role == "viewer"


def test_resolve_role_matched_default_admin(policy):
    assert policy.resolve_role("viewer") == "viewer"
    assert policy.resolve_role("admin") == "admin"
    # 未列出来源 → 回退 default_role(viewer)
    assert policy.resolve_role("someone-else") == "viewer"


def test_resolve_role_no_default():
    p = Policy.from_json(json.dumps({"roles": {"admin": {"tables": None}}}))
    assert p.resolve_role("unknown") is None  # 无 default → 入口应拒绝


# ---- 列级提取（fail-closed）----
def test_extract_columns_explicit_prefix():
    assert extract_columns("SELECT sales.a, sales.b FROM sales", "sales") == {"a", "b"}


def test_extract_columns_not_in_sql():
    assert extract_columns("SELECT x FROM other", "sales") is None


def test_extract_columns_select_star_raises():
    with pytest.raises(ValueError):
        extract_columns("SELECT * FROM sales", "sales")


def test_extract_columns_unparseable_raises():
    # DELETE 无 SELECT 子句：可定位到表但无法解析列 → fail-closed raise
    with pytest.raises(ValueError):
        extract_columns("DELETE FROM sales WHERE id=1", "sales")


# ---- 组合守卫 additive ----
async def _fake_is_allowed_table_async(table):
    return table  # 不触库：替换 is_allowed_table，只验证 RBAC 层逻辑


def test_build_table_guards_no_policy_returns_none():
    assert build_role_guards(None, "viewer") == (None, None)
    assert build_role_guards(Policy(roles={}), None) == (None, None)


def test_role_table_denied(monkeypatch):
    monkeypatch.setattr(boundaries, "is_allowed_table", _fake_is_allowed_table_async)
    policy = Policy.from_json(json.dumps({
        "roles": {"viewer": {"tables": ["sales"]}},
    }))
    tcheck, _ = build_role_guards(policy, "viewer")
    asyncio.run(tcheck("sales"))            # 允许
    with pytest.raises(ValueError):
        asyncio.run(tcheck("physical"))     # 角色白名单之外 → 拒绝


def test_role_table_allowed_under_system(monkeypatch):
    monkeypatch.setattr(boundaries, "is_allowed_table", _fake_is_allowed_table_async)
    policy = Policy.from_json(json.dumps({
        "roles": {"viewer": {"tables": ["sales"]}},
    }))
    tcheck, _ = build_role_guards(policy, "viewer")
    asyncio.run(tcheck("sales"))


def test_guard_column_denied(monkeypatch):
    monkeypatch.setattr(boundaries, "is_allowed_table", _fake_is_allowed_table_async)
    policy = Policy.from_json(json.dumps({
        "roles": {"viewer": {"tables": ["sales"], "columns": {"sales": ["a", "b"]}}},
    }))
    _, ccheck = build_role_guards(policy, "viewer")
    asyncio.run(ccheck("SELECT sales.a, sales.b FROM sales"))  # 允许的列
    with pytest.raises(ValueError):
        asyncio.run(ccheck("SELECT sales.secret FROM sales"))  # 越权列 → 拒绝


def test_guard_column_passdown_to_guard():
    """列白名单经 guard_query_sql 的 column_checker 参数生效（additive，不触库）。"""
    policy = Policy.from_json(json.dumps({
        "roles": {"viewer": {"tables": ["sales"], "columns": {"sales": ["a"]}}},
    }))
    _, ccheck = build_role_guards(policy, "viewer")

    async def fake_table_checker(_t):
        return _t

    sql, err = asyncio.run(guard_query_sql_on(
        "SELECT sales.a FROM sales", fake_table_checker, ccheck))
    assert err is None
    sql2, err2 = asyncio.run(guard_query_sql_on(
        "SELECT sales.secret FROM sales", fake_table_checker, ccheck))
    assert err2 is not None and "越权列" in err2


async def guard_query_sql_on(q, tc, cc):
    return await boundaries.guard_query_sql(q, table_checker=tc, column_checker=cc)