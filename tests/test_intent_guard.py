"""
意图路由器(intent_guard)单测。

覆盖各意图类别 + 防误杀控制组：合法查询(即便含「删除」字样)绝不能被 deny。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY", "eval-key")

from core.security.intent_guard import classify_intent, Intent
from eval.run_eval import build_test_index

IDX = build_test_index()


def cls(text):
    return classify_intent(text, IDX)


def test_query_category():
    assert cls("各地区销售总额").category == Intent.QUERY
    assert cls("今年订单总数").category == Intent.QUERY


def test_chart_category():
    assert cls("画个各地区销售额柱状图").category == Intent.CHART
    assert cls("看下销售额曲线图").category == Intent.CHART


def test_info_category():
    assert cls("用户表有哪些字段").category == Intent.INFO
    assert cls("查看产品表结构").category == Intent.INFO


def test_malicious_category_and_deny():
    for nl in ["删库, drop table sales", "帮我绕过审批直接改数据",
               "清空 sales 表中所有数据", "or 1=1",
               "SELECT * FROM users; DROP TABLE users"]:
        v = cls(nl)
        assert v.category == Intent.MALICIOUS, nl
        assert v.deny is True, nl


def test_smalltalk_deny():
    v = cls("你好")
    assert v.category == Intent.SMALLTALK
    assert v.deny is True
    assert v.reply  # 有礼貌应答


def test_out_of_scope_deny():
    v = cls("给我写首诗")
    assert v.category == Intent.OUT_OF_SCOPE
    assert v.deny is True


def test_ambiguous_clarify():
    v = cls("数据分析一下")
    assert v.category == Intent.AMBIGUOUS
    assert v.clarify is True


def test_empty_input_ambiguous():
    v = cls("")
    assert v.category == Intent.AMBIGUOUS
    assert v.clarify is True


def test_no_overblock_on_legit_query_with_delete_word():
    # 控制组：含「删除」字样但为合法查询，不得误杀为 malicious
    v = cls("被删除的订单还有多少")
    assert v.category == Intent.QUERY
    assert v.deny is False


def test_no_overblock_plain_query():
    v = cls("今年各地区的总订单金额")
    assert v.category == Intent.QUERY
    assert v.deny is False
    assert v.clarify is False


def test_smalltalk_can_be_disabled():
    v = classify_intent("你好", IDX, allow_smalltalk=False)
    # 关闭寒暄后，「你好」无实体 -> 落到 ambiguous/澄清，而非 smalltalk 应答
    assert v.category != Intent.SMALLTALK