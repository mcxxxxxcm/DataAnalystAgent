"""
配置管理

为什么使用pydantic-settings:
1、类型安全：自动类型转换和验证
2、环境变量：支持从.env文件和系统环境变量加载
3、集中管理：所有配置在一个地方，便于维护
4、默认值：为开发环境提供合理的默认值
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, Union, Dict, List
from functools import lru_cache
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# 少设置约定（Few-Settings）：运行时一次性 / 常量类参数（如缓存 TTL、容量上限）以各模块
# 常量/缓存原语为准，不进配置；只有真实被消费且需按部署调整的参数才在此定义（见 design 状态所有权）。


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
    llm_context_window: Optional[int] = Field(
        default=None,
        description="模型上下文窗口大小(token)。留空时按 llm_model 推断；用于推导消息裁剪/摘要预算"
    )

    # === 提示词缓存（省计费） ===
    prompt_cache_enabled: bool = Field(
        default=False,
        description=("是否采用「固定前缀置顶、动态段置尾」的提示词布局，以命中支持自动磁盘缓存的 provider。"
                     "降固定提示词的重复计费。关闭（默认）时系统提示词逐字节不变")
    )
    prompt_cache_header_json: str = Field(
        default="",
        description=("显式 cache 头 JSON 字面量（如 anthropic 风格 cache_control），在开启提示词缓存时注入。"
                     "空=不注入。不同 provider 头格式不一，需按自身 API 配置")
    )

    # === 数据库配置 ===
    db_host: str = Field(default="localhost", description="数据库主机地址")
    db_port: int = Field(default=5432, ge=1, le=65535, description="数据库端口")
    db_name: str = Field(default="analytics", description="数据库名称")
    db_user: str = Field(default="postgres", description="数据库用户名")
    db_password: str = Field(default="", description="数据库密码")
    db_pool_size: int = Field(default=20, ge=1, le=100, description="连接池最大大小")
    db_pool_min_size: int = Field(default=5, ge=1, le=100, description="连接池最小大小(预warm)")

    # === 安全配置 ===
    sql_max_rows: int = Field(default=10000, ge=1, description="SQL查询最大返回行数，防止全表扫描")
    sql_timeout: int = Field(default=30, ge=1, description="SQL执行超时时间(S)")
    enable_sql_write: bool = Field(default=False, description="是否允许写操作(INSERT/UPDATE/DELETE)")
    enable_intent_router: bool = Field(
        default=False,
        description=("是否在 /query 入口接入确定性意图路由器(intent_guard)做前置拒答/澄清。"
                     "默认关：当前路由器仅由评测(eval/run_eval.py)直接调用，不改运行时行为"
                     "（core/security/intent_guard.classify_intent 为纯函数，与开关无关）")
    )
    enable_admission_gate: bool = Field(
        default=False,
        description=("是否在 /query 入口启用请求准入门(admission gate)：来源×意图合成准入判定，"
                     "未准入来源拒绝、低信号安全意图(寒暄/结构询问)用固定文案直答不烧 LLM。"
                     "默认关，接通不改变现状（core/security/admission.py 为纯逻辑）。")
    )
    admission_mode: str = Field(
        default="off",
        description="准入门来源模式: off=不校验来源(仅意图判定) / allowlist=校验 admission_allowed_keys。"
    )
    admission_allowed_keys: Optional[str] = Field(
        default=None,
        description="allowlist 模式允许的来源 key（逗号分隔）。来源由请求头 X-Admission-Key 提供。"
    )
    intent_canonical_replies: Optional[str] = Field(
        default=None,
        description="低信号安全意图的固定直答文案（prompt text，非 LLM 生成），'意图=文案' 逗号分隔段，"
                    "如 'smalltalk=你好，我是数据分析助手...'。未配置时用 intent_guard 内置兜底文案。"
    )

    # === RBAC / 限流（最小授权） ===
    enable_rbac: bool = Field(
        default=False,
        description="是否启用表/列级 RBAC 与来源限流。默认关：关闭时守卫/鉴权路径与现状一致，零改动"
    )
    rbac_policy_json: str = Field(
        default="",
        description=("RBAC 角色策略 JSON 字面量或 '@相对路径'。roles.name.tables/columns/主要；"
                     "default_role 供未列出来源回退（None=未匹配拒绝）。仅 enable_rbac=True 生效")
    )
    rbac_rate_limit: str = Field(
        default="",
        description="来源/令牌级滑动窗口限流，如 '10/min'、'1000/h'。空=不启用。仅 enable_rbac=True 生效"
    )

    # === 工具配置 ===
    enable_custom_chart: bool = Field(
        default=False,
        description="是否启用 create_custom_chart（允许LLM生成并执行任意绘图代码，风险较高，默认关闭）"
    )
    default_tool_scope: str = Field(
        default="full",
        description="默认工具范围: full / read_only / query_only。full=全部；read_only=排除导出与自定义绘图；query_only=仅SQL查询工具"
    )
    tool_thread_pool_size: int = Field(
        default=4,
        ge=1,
        le=32,
        description="阻塞型工具计算(统计/数据探查/图表构建)共享的线程池 worker 数"
    )

    # === Schema Linking（相关表检索） ===
    schema_max_relevant_tables: int = Field(
        default=3,
        ge=1,
        le=10,
        description="get_relevant_schemas 单次返回的最大相关表数"
    )
    schema_value_profiling: bool = Field(
        default=False,
        description="是否对 top 候选表的低基数字符串列抓 distinct 样例值(帮助 LLM 猜过滤条件，略增查询开销)"
    )
    schema_synonyms: Optional[str] = Field(
        default=None,
        description="可选的用户自定义同义词映射，逗号分隔的 '词=表A,表B' 段，如 '业绩=sales,购买=orders'"
    )
    schema_embed_enabled: bool = Field(
        default=False,
        description="是否在 get_relevant_schemas 启用语义重排（关键词仍打底，语义仅作增量校准）。默认关零行为变化"
    )
    schema_embed_fn: Optional[str] = Field(
        default=None,
        description="可选的 embedder 点分导入路径：工厂形如 f() -> callable(query, table_text) -> float 相似度[0,1]。空=不启用"
    )

    # === 缓存后端 ===
    cache_backend: str = Field(
        default="memory",
        description=("结果/图表缓存后端: memory=进程内存(默认) / redis=跨 worker 共享。"
                     "redis 需装 redis[asyncio] 且配置 redis_url；连不上自动回退 memory")
    )
    redis_url: str = Field(
        default="",
        description=("Redis 连接串（cache_backend=redis 时用），如 redis://localhost:6379/0。"
                     "默认为空=不启用 Redis 共享缓存。此配置在少设置审计(few-settings)中曾删除，"
                     "B006 明确需要一个可选共享缓存落点后重新引入，默认空不影响 memory 默认行为")
    )

    # === 可观测 ===
    observability_enabled: bool = Field(
        default=False,
        description="是否启用可观测指标采集与 /api/metrics 端点（Prometheus 文本格式）。默认关，关闭时采集均为 no-op"
    )

    # === 人工审核 / 审计 ===
    audit_log_enabled: bool = Field(
        default=True,
        description="是否记录审批/拒绝等人工审核决策到 audit.jsonl"
    )
    recon_model_view_enabled: bool = Field(
        default=True,
        description="是否在工具调用日志记录 model_view(与送入LLM同阈值裁剪的内容)，供会话重建/审计"
    )

    # === 记忆 / 长期记忆 Store ===
    enable_memory_tools: bool = Field(
        default=True,
        description="是否启用 remember/recall 长期记忆工具(需启用 PostgresStore)"
    )

    # === 工具返回载荷裁剪（送入 LLM 前） ===
    tool_result_max_rows: int = Field(
        default=20,
        ge=1,
        le=1000,
        description="工具返回 data 保留的最大行数，超出部分裁剪"
    )
    tool_result_max_chars_per_cell: int = Field(
        default=200,
        ge=1,
        le=10000,
        description="工具返回单个单元格允许的最大字符数，超出截断"
    )
    tool_result_max_content_len: int = Field(
        default=8000,
        ge=100,
        le=1000000,
        description="非结构化工具载荷的字符上限"
    )

    # === 导出配置 ===
    export_dir: str = Field(
        default="exports",
        description="导出文件目录（相对项目根目录）"
    )
    export_max_rows: int = Field(
        default=10000,
        ge=1,
        le=100000,
        description="导出/统计采样最大行数"
    )

    # === Agent配置 ===
    max_retry_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="SQL执行失败时的最大重试次数"
    )
    sql_retry_on_transient: bool = Field(
        default=True,
        description="对瞬时/可恢复类 SQL 错误(超时、死锁、连接中断等)自动重试(经 ToolRetryMiddleware)"
    )
    effect_queue_max_retries: int = Field(
        default=2, ge=0, le=10,
        description="SQL 瞬时错误经效果队列(utils/effect_queue)的指数退避重试次数上限；0=关闭退避层"
    )
    effect_queue_base_delay: float = Field(
        default=1.0, ge=0.1, le=60.0,
        description="SQL 效果队列指数退避的基础延迟(秒)，实际退避 = base × 2^(attempt)"
    )

    # === API配置 ===
    api_host: str = Field(default="0.0.0.0", description="API服务监听地址")
    api_port: int = Field(default=8080, description="API服务端口")
    api_workers: int = Field(default=1, description="API工作进程数，异步应用建议单worker")
    api_backlog: int = Field(default=2048, ge=64, description="uvicorn 等待队列 backlog 上限")
    api_keepalive: int = Field(default=5, ge=1, description="uvicorn keep-alive 超时(秒)")
    api_graceful_shutdown: int = Field(default=30, ge=1, description="uvicorn 优雅停机等待(秒)")
    api_reload: bool = Field(
        default=False,
        description="是否启用 uvicorn 自动重载（仅开发环境建议开启）"
    )
    api_auth_token: Optional[str] = Field(
        default=None,
        description="可选Bearer Token鉴权。为空则不开启鉴权；生产环境建议设置"
    )
    cors_origins: str = Field(
        default="*",
        description="允许的CORS来源，逗号分隔，如: http://localhost:3000,https://app.example.com"
    )

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

    @property
    def cors_origin_list(self) -> list:
        """解析CORS来源列表（逗号分隔）"""
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins or ["*"]

    @property
    def is_cors_open(self) -> bool:
        """CORS是否全放开（包含通配符 * ）"""
        return "*" in self.cors_origin_list

    @property
    def context_budget(self) -> int:
        """
        推导可用于消息/工具的上下文预算(token)。

        规则：优先用显式 llm_context_window；否则按常见模型窗口上下限做推断；
        再乘 0.8 作为「建议占用上限」，给本轮 tool 参数与模型输出留 20% 余量。
        """
        window = self.llm_context_window or _infer_context_window(self.llm_model)
        return int(window * 0.8)

    @property
    def allowed_admission_keys(self) -> set:
        """解析 admission_allowed_keys 为允许的来源 key 集合（allowlist 模式用）。"""
        if not self.admission_allowed_keys:
            return set()
        return {k.strip().lower() for k in self.admission_allowed_keys.split(',') if k.strip()}

    @property
    def canonical_reply_map(self) -> Dict[str, str]:
        """解析 intent_canonical_replies 为 {意图: 文案}（注意力经济的固定直答文案）。"""
        mapping: Dict[str, str] = {}
        if not self.intent_canonical_replies:
            return mapping
        for segment in self.intent_canonical_replies.split(','):
            segment = segment.strip()
            if not segment or '=' not in segment:
                continue
            intent, _, reply = segment.partition('=')
            intent, reply = intent.strip().lower(), reply.strip()
            if intent and reply:
                mapping[intent] = reply
        return mapping

    @property
    def user_synonym_map(self) -> Dict[str, List[str]]:
        """
        解析 schema_synonyms 为用户同义词表：{同义词: [表A, 表B]}。
        段格式: '业绩=sales,购买=orders'（段用逗号，表用顿号/逗号分隔）。
        """
        mapping: Dict[str, List[str]] = {}
        if not self.schema_synonyms:
            return mapping
        for segment in self.schema_synonyms.split(','):
            segment = segment.strip()
            if not segment or '=' not in segment:
                continue
            word, _, tables = segment.partition('=')
            word, tables = word.strip().lower(), tables.strip()
            if word and tables:
                mapping[word] = [t.strip().lower() for t in tables.replace('、', ',').split(',') if t.strip()]
        return mapping

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

def _infer_context_window(model: str) -> int:
    """
    由模型名推断上下文窗口(token)的粗略兜底。
    None(显式已给) 或未知名 → 128k（LLM 时代基线）。
    """
    m = model.lower()
    if '1.5-pro' in m or '2.0' in m or 'claude-3-5-sonnet' in m or 'gpt-4o' in m or 'glm-4-plus' in m:
        return 128000
    if '1.5-flash' in m or 'gpt-4' in m or 'glm-4' in m or 'deepseek' in m:
        return 128000
    return 128000


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