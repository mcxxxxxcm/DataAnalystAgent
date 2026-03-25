"""
配置管理

为什么使用pydantic-settings:
1、类型安全：自动类型转换和验证
2、环境变量：支持从.env文件和系统环境变量加载
3、集中管理：所有配置在一个地方，便于维护
4、默认值：为开发环境提供合理的默认值
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
from functools import lru_cache
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()


class Settings(BaseSettings):
    """
    应用配置类

    所有配置项都有类型提示和默认值
    支持从环境变量或env文件加载
    """
    # === LLM 配置 ===
    api_key: str = Field(..., description="APIKEY，必填")
    base_url: Optional[str] = Field(None, description="API基础URL")
    llm_model: str = Field("gpt-4-turbo", description="LLM模型名称")
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="模型温度参数，越低越确定。"
    )
    llm_max_tokens: int = Field(default=4096, description="最大token数")

    # === 数据库配置 ===
    db_host: str = Field(default="localhost", description="数据库主机地址")
    db_port: int = Field(default=5432, ge=1, le=65535, description="数据库端口")
    db_name: str = Field(default="analytics", description="数据库名称")
    db_user: str = Field(default="postgres", description="数据库用户名")
    db_password: str = Field(default="", description="数据库密码")
    db_pool_size: int = Field(default=10, ge=1, le=100, description="连接池大小")
    db_max_overflow: int = Field(default=20, description="最大溢出连接数")

    # === 安全配置 ===
    sql_max_rows: int = Field(default=10000, ge=1, description="SQL查询最大返回行数，防止全表扫描")
    sql_timeout: int = Field(default=30, ge=1, description="SQL执行超时时间(S)")
    enable_sql_write: bool = Field(default=False, description="是否允许写操作(INSERT/UPDATE/DELETE)")

    # === Redis缓存配置 ===
    redis_url: Optional[str] = Field(default=None, description="Redis连接URL，用于缓存Schema和查询结果")
    cache_ttl: int = Field(default=3600, description="缓存过期时间(S)")

    # === Agent配置 ===
    max_retry_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="SQL执行失败时的最大重试次数"
    )
    agent_verbose: bool = Field(default=True, description="是否显示详细日志")

    # === API配置 ===
    api_host: str = Field(default="0.0.0.0", description="API服务监听地址")
    api_port: int = Field(default=8080, description="API服务端口")
    api_workers: int = Field(default=1, description="API工作进程数，异步应用建议单worker")

    @property
    def db_connection_string(self) -> str:
        """
        生成数据库连接字符串

        为什么用属性方法：
        1、动态生成，不需要存储
        2、自动同步配变更
        """
        return (
            f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def async_db_connection_string(self) -> str:
        """异步数据库连接字符串"""
        return (
            f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例

    为什么使用lru_cache：
    1、单理模式：确保全局只有一个配置实例
    2、性能优化：避免重复读取环境变量和文件
    3、线程安全：lru_cache是线程安全的
    """
    return Settings()

# 配置验证函数
def validate_settings()->None:
    """
    验证配置是否完整

    在应用启动时调用提前发现配置问题
    """
    settings = get_settings()

    # 检查必要配置
    if not settings.api_key:
        raise ValueError("缺少必要配置：API_KEY")

    if not settings.db_password:
        print("警告：数据库密码为空，请确认是否正确")

    print(f"配置加载成功:")
    print(f"  - LLM模型: {settings.llm_model}")
    print(f"  - 数据库: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    print(f"  - SQL最大行数: {settings.sql_max_rows}")
    print(f"  - 允许写操作: {settings.enable_sql_write}")

if __name__ == '__main__':
    validate_settings()