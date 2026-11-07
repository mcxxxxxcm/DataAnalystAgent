"""
eval.mine_badcases 的 --sink-security 沉淀逻辑测试。

覆盖 propose_security_denies：按规范化 SQL 去重、跳过已存在、只收 query_database 中被安全层拒绝的调用。
纯逻辑，不读真实日志。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from eval.mine_badcases import _norm_sql, propose_security_denies, _is_security_reject_error


def _record(tool="query_database", sql="SELECT 1", error="SQL 校验失败: 不允许", success=False,
            args=None):
    input_args = args or {"query": sql}
    return {"tool_name": tool, "input_args": input_args, "error": error, "success": success}


def test_norm_sql_ignores_whitespace_and_case():
    assert _norm_sql("  SELECT * FROM t WHERE x=1  ") == _norm_sql("select * from t where x=1")


def test_norm_sql_strips_trailing_semicolon():
    assert _norm_sql("SELECT 1;") == _norm_sql("SELECT 1")


def test_propose_dedups_by_normalized_sql():
    recs = [
        _record(sql="SELECT * FROM t WHERE 1=1"),
        _record(sql="select * from t where 1=1"),   # 等价 → 去重
    ]
    out = propose_security_denies(recs, existing_sqls=[])
    assert len(out) == 1


def test_propose_skips_existing():
    recs = [_record(sql="SELECT * FROM t WHERE 1=1")]
    out = propose_security_denies(recs, existing_sqls=["SELECT * FROM t WHERE 1=1"])
    assert out == []


def test_propose_only_accepts_query_database_and_security_reject():
    bad_tool = _record(tool="create_chart", sql="...", error="校验失败")
    not_security_error = _record(tool="query_database", sql="SELECT * FROM t",
                                 error="relation does not exist")
    sec_deny = _record(tool="query_database", sql="SELECT * FROM t WHERE 1=1", error="SQL 校验失败")
    recs = [bad_tool, not_security_error, sec_deny]
    out = propose_security_denies(recs, existing_sqls=[])
    assert [c["sql"] for c in out] == [sec_deny["input_args"]["query"]]


def test_proposed_case_shape():
    recs = [_record(sql="DROP TABLE t", error="查询被安全策略拒绝")]
    out = propose_security_denies(recs, existing_sqls=[])
    assert out
    c = out[0]
    assert c["scenario"] == "security_deny"
    assert c["deny_expected"] is True
    assert c["source"] == "log"
    assert c["id"].startswith("sec-auto-")


def test_security_error_hints():
    assert _is_security_reject_error("SQL 校验失败: 注入")
    assert _is_security_reject_error("查询被安全策略拒绝（最低风险要求未满足）")
    assert not _is_security_reject_error("relation 'sales' does not exist")