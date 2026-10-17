"""
确定性回归评测的 pytest 硬门槛包装。

把 eval/cases/ 三类语料纳入测试套件，重点保证：
- 全量用例 0 失败（防 schema / 安全 / 路由改动退化）。
- security_deny「该拒必拒（误放行=0）」+「合法 SELECT 不误杀」。
- routing_guard「拒绝类必 deny、歧义必 clarify」。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from core.security.sql_validator import SQLValidator
from core.security.intent_guard import classify_intent
from eval.run_eval import build_test_index, run_suite, _load_case_files

_REJECT_CATS = {"malicious", "smalltalk", "out_of_scope"}


def _suite():
    idx = build_test_index()
    val = SQLValidator(max_rows=100, enable_write=False, timeout=30)
    return run_suite(_load_case_files(), idx, val)


def test_full_eval_suite_passes():
    s = _suite()
    assert s.cases["fail"] == 0, f"回归评测有 {s.cases['fail']} 项失败: {s.details}"


def test_security_deny_no_false_accept():
    """该拒的写操作/DDL/注入必须全部被拒（误放行=0）。"""
    val = SQLValidator(max_rows=100, enable_write=False, timeout=30)
    bad = [c for c in _load_case_files()
           if c["scenario"] == "security_deny" and c.get("deny_expected")]
    assert bad, "security_deny 缺少 deny 用例"
    for c in bad:
        assert not val.validate(c["sql"]).is_valid, f"[{c['id']}] 该拒未拒: {c['sql']}"


def test_security_accept_no_false_deny():
    """控制组：合法 SELECT 不能被误杀。"""
    val = SQLValidator(max_rows=100, enable_write=False, timeout=30)
    ok = [c for c in _load_case_files()
          if c["scenario"] == "security_deny" and not c.get("deny_expected")]
    assert ok, "security_deny 缺少放行控制组"
    for c in ok:
        assert val.validate(c["sql"]).is_valid, f"[{c['id']}] 误杀合法查询: {c['sql']}"


def test_routing_guard_deny_semantics():
    """拒绝类必 deny、歧义必 clarify（路由决定不能自相矛盾）。"""
    idx = build_test_index()
    cases = [c for c in _load_case_files() if c["scenario"] == "routing_guard"]
    for c in cases:
        vd = classify_intent(c["nl"], idx)
        exp = c["expected_category"]
        if exp in _REJECT_CATS:
            assert vd.deny, f"[{c['id']}] 拒绝类 {exp} 未 deny: {c['nl']}"
        elif exp == "ambiguous":
            assert vd.clarify, f"[{c['id']}] 歧义未 clarify: {c['nl']}"
        else:
            assert not vd.deny and not vd.clarify, f"[{c['id']}] 放行类被误拦: {c['nl']}"