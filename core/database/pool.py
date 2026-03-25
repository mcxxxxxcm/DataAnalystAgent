"""
数据库连接池管理

位置：core/database/pool.py
职责：提供数据库连接能力，不暴露给LLM
"""

import asyncpg
from typing import Optional, List, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import asyncio
from functools import wraps

from config.settings import get_settings


@dataclass
class PoolStats:
    """连接池统计信息"""
    size: int
    min_size: int
    max_size: int
    idle_size: int


class DatabasePool:
    """
    数据库连接池管理器（单例）

    这是基础设施，不暴露给LLM
    只被 tools/ 和 middleware/ 内部调用
    """

    _instance: Optional['DatabasePool'] = None
    _pool: Optional[asyncpg.Pool] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self) -> None:
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
        print(f"数据库连接池初始化完成: {settings.db_host}:{settings.db_port}/{settings.db_name}")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """获取连接"""
        if not self._initialized or self._pool is None:
            raise RuntimeError("连接池未初始化")

        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args, timeout: Optional[float] = None) -> str:
        """执行SQL（无返回）"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def fetch(self, query: str, *args, timeout: Optional[float] = None) -> List[asyncpg.Record]:
        """执行查询"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None) -> Optional[asyncpg.Record]:
        """查询单行"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def fetchval(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """查询单值"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)

    async def close(self) -> None:
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    def get_stats(self) -> PoolStats:
        """获取统计信息"""
        if not self._pool:
            return PoolStats(0, 0, 0, 0)
        return PoolStats(
            size=self._pool.get_size(),
            min_size=self._pool.get_min_size(),
            max_size=self._pool.get_max_size(),
            idle_size=self._pool.get_idle_size()
        )


# 全局单例
db_pool = DatabasePool()