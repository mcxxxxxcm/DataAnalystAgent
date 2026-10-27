"""
config.settings 新增并发相关配置默认值断言
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_KEY", "test-key-for-unit-test")


def test_concurrency_defaults():
    from config.settings import Settings

    s = Settings(_env_file=None)  # 忽略 .env，测代码默认值
    assert s.db_pool_min_size == 5
    assert s.db_pool_size == 20
    assert s.tool_thread_pool_size == 4
    assert s.api_backlog == 2048
    assert s.api_keepalive == 5
    assert s.api_graceful_shutdown == 30


def test_db_max_overflow_deprecated_but_kept():
    from config.settings import Settings

    s = Settings(_env_file=None)
    # 字段保留（避免 .env 同名变量被 extra=ignore 静默吞掉），但默认 0 表示废弃
    assert s.db_max_overflow == 0