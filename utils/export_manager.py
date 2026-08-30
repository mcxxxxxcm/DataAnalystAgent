"""
导出文件管理器

位置：utils/export_manager.py
职责：将查询结果落盘为 CSV/Excel，并维护进程内的文件注册表

设计：
- 导出目录：PROJECT_ROOT / export_dir（默认 exports/，见 settings）
- 文件名由服务端用 uuid 生成，杜绝用户输入导致的路径穿越
- registry 为内存注册表（进程内有效），供 /export/{file_id} 下载端点取文件
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from config.settings import get_settings, PROJECT_ROOT

EXPORT_FORMATS = {"csv", "xlsx"}

_media_types = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass
class ExportFile:
    """导出的文件信息"""
    file_id: str
    filename: str
    path: Path
    format: str


class ExportManager:
    """导出文件管理器"""

    def __init__(self):
        self._registry: Dict[str, ExportFile] = {}

    def _resolve_dir(self) -> Path:
        base = PROJECT_ROOT / get_settings().export_dir
        base.mkdir(parents=True, exist_ok=True)
        return base

    def save_dataframe(
            self,
            df: pd.DataFrame,
            file_format: str = "csv",
            filename: Optional[str] = None
    ) -> ExportFile:
        """将 DataFrame 落盘，返回文件注册信息"""
        if file_format not in EXPORT_FORMATS:
            raise ValueError(f"不支持的导出格式: {file_format}，可选: {sorted(EXPORT_FORMATS)}")

        file_id = uuid.uuid4().hex[:12]
        ext = "xlsx" if file_format == "xlsx" else "csv"
        name = filename or f"export_{file_id}"
        if "." not in name:
            name = f"{name}.{ext}"
        path = self._resolve_dir() / f"{file_id}_{name}"

        if file_format == "csv":
            df.to_csv(path, index=False)
        else:
            df.to_excel(path, index=False)

        export_file = ExportFile(
            file_id=file_id,
            filename=name,
            path=path,
            format=file_format,
        )
        self._registry[file_id] = export_file
        return export_file

    def get_export(self, file_id: str) -> Optional[ExportFile]:
        """按 file_id 获取导出的文件信息"""
        entry = self._registry.get(file_id)
        if entry is None:
            return None
        if not entry.path.exists():
            self._registry.pop(file_id, None)
            return None
        return entry

    def media_type(self, file_format: str) -> str:
        return _media_types.get(file_format, "application/octet-stream")


export_manager = ExportManager()