"""
本地日志中间件

位置：middleware/logging_middleware.py
职责：本地记录所有操作，不发送到外部服务

设计原则：
1. 所有日志存储在本地
2. 敏感数据自动脱敏
3. 支持结构化日志（JSON格式）
4. 支持日志轮转，防止磁盘占满
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    record_id: str
    timestamp: str
    thread_id: str
    tool_name: str
    input_args: Dict[str, Any]
    output: Optional[str] = None
    success: bool = True
    execution_time_ms: float = 0.0
    error: Optional[str] = None

    def to_json(self) -> str:
        """转换为JSON"""
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


class LocalLogger:
    """
    本地日志记录器

    特点：
    1. 日志存储在本地文件
    2. 自动脱敏敏感信息
    3. 支持日志轮转
    4. 支持按日期/会话查询
    """

    # 敏感字段（需要脱敏）
    SENSITIVE_FIELDS = {
        'password', 'secret', 'token', 'key', 'credential',
        'api_key', 'apikey', 'auth', 'private'
    }

    def __init__(
            self,
            log_dir: str = "./logs",
            max_file_size: int = 10 * 1024 * 1024,  # 10MB
            backup_count: int = 5,
            log_level: int = logging.INFO
    ):
        """
        初始化本地日志记录器

        参数:
            log_dir: 日志目录
            max_file_size: 单个日志文件最大大小
            backup_count: 保留的日志文件数量
            log_level: 日志级别
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 创建日志记录器
        self.logger = logging.getLogger("DataAnalystAgent")
        self.logger.setLevel(log_level)

        # 清除已有的处理器
        self.logger.handlers.clear()

        # 文件处理器 - 主日志
        main_log_file = self.log_dir / "agent.log"
        file_handler = RotatingFileHandler(
            main_log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(file_handler)

        # 文件处理器 - 工具调用日志（单独存储）
        tool_log_file = self.log_dir / "tool_calls.jsonl"
        self.tool_log_handler = RotatingFileHandler(
            tool_log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        self.logger.addHandler(self.tool_log_handler)

        # 控制台处理器（开发环境）
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(console_handler)

        # 内存缓存（用于查询最近记录）
        self._recent_records: list = []
        self._max_recent = 100

    def _generate_record_id(self, tool_name: str, timestamp: str) -> str:
        """生成记录ID"""
        data = f"{tool_name}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:12]

    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        脱敏敏感参数

        防止密码、密钥等敏感信息被记录
        """
        sanitized = {}

        for key, value in args.items():
            key_lower = key.lower()

            # 检查是否是敏感字段
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_FIELDS):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 1000:
                # 截断过长的字符串
                sanitized[key] = value[:1000] + "...[truncated]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_args(value)
            else:
                sanitized[key] = value

        return sanitized

    def _truncate_output(self, output: Optional[str], max_length: int = 2000) -> Optional[str]:
        """截断过长的输出"""
        if output and len(output) > max_length:
            return output[:max_length] + "...[truncated]"
        return output

    def log_tool_call(
            self,
            thread_id: str,
            tool_name: str,
            input_args: Dict[str, Any],
            output: Optional[str] = None,
            success: bool = True,
            execution_time_ms: float = 0.0,
            error: Optional[str] = None
    ) -> str:
        """
        记录工具调用

        返回:
            记录ID
        """
        timestamp = datetime.now().isoformat()
        record_id = self._generate_record_id(tool_name, timestamp)

        record = ToolCallRecord(
            record_id=record_id,
            timestamp=timestamp,
            thread_id=thread_id,
            tool_name=tool_name,
            input_args=self._sanitize_args(input_args),
            output=self._truncate_output(output),
            success=success,
            execution_time_ms=execution_time_ms,
            error=error
        )

        # 写入日志文件（JSONL格式，每行一个JSON）
        tool_log_path = self.log_dir / "tool_calls.jsonl"
        with open(tool_log_path, 'a', encoding='utf-8') as f:
            f.write(record.to_json() + '\n')

        # 记录到主日志
        status = "成功" if success else "失败"
        self.logger.info(
            f"[工具调用] {tool_name} ({status}, {execution_time_ms:.2f}ms) "
            f"[thread={thread_id}, record={record_id}]"
        )

        if error:
            self.logger.error(f"[工具调用错误] {tool_name}: {error}")

        # 缓存最近记录
        self._recent_records.append(record)
        if len(self._recent_records) > self._max_recent:
            self._recent_records.pop(0)

        return record_id

    def get_recent_records(self, limit: int = 10) -> list:
        """获取最近的记录"""
        return [asdict(r) for r in self._recent_records[-limit:]]

    def get_records_by_thread(self, thread_id: str) -> list:
        """按会话ID查询记录"""
        return [
            asdict(r) for r in self._recent_records
            if r.thread_id == thread_id
        ]

    def query_records(
            self,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            tool_name: Optional[str] = None,
            success_only: bool = False
    ) -> list:
        """
        查询历史记录

        从日志文件中读取
        """
        results = []
        tool_log_path = self.log_dir / "tool_calls.jsonl"

        if not tool_log_path.exists():
            return results

        with open(tool_log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())

                    # 过滤条件
                    if start_time and record['timestamp'] < start_time:
                        continue
                    if end_time and record['timestamp'] > end_time:
                        continue
                    if tool_name and record['tool_name'] != tool_name:
                        continue
                    if success_only and not record['success']:
                        continue

                    results.append(record)
                except json.JSONDecodeError:
                    continue

        return results

    def log_agent_event(
            self,
            event_type: str,
            thread_id: str,
            message: str,
            metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        记录Agent事件

        参数:
            event_type: 事件类型（start, end, interrupt, resume等）
            thread_id: 会话ID
            message: 事件消息
            metadata: 额外元数据
        """
        self.logger.info(
            f"[Agent事件] {event_type} [thread={thread_id}] {message}"
        )

        if metadata:
            self.logger.debug(f"[元数据] {json.dumps(metadata, ensure_ascii=False)}")


# 全局实例
local_logger = LocalLogger()