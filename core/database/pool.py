"""
数据库连接池管理： 提供数据库连接能力，不暴露给LLM
"""

import asyncpg
from typing import Optional, List, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import asyncio
from functools import wraps
from config.settings import get_settings


@dataclass
class PoolState:
    """连接池统计信息"""
    size: int
    min_size: int
    max_size: int
    idle_size: int

class DatabasePool:
    """
    数据库连接池管理器（单例）
    """

    _instance: Optional['DatabasePool'] = None
    _pool: Optional[asyncpg.Pool] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self)-> None:
        """初始化连接池"""
        if self._initialized:
            return

        settings = get_settings()

        self._pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=5,
            max_size=settings.db_pool_size,
            command_timeout=settings.sql_timeout,
        )

        self._initialized = True
        print(f"数据库连接池初始化完成：{settings.db_host}:{settings.db_port}/{settings.db_name}")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """获取连接"""
        if not self._initialized or self._pool is None:
            raise RuntimeError("连接池未初始化")