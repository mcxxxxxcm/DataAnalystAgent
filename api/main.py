"""
应用主入口

位置：api/main.py
职责：FastAPI 应用配置和启动
支持短期记忆（多轮对话上下文保持）
"""

import sys
import os
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from config.settings import get_settings, validate_settings
from core.database import db_pool
from api.routes import router
from middleware import setup_checkpointer, close_checkpointer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    应用生命周期管理

    启动时：
    1. 验证配置
    2. 初始化数据库连接池
    3. 初始化 checkpointer 数据库表（短期记忆）
    4. 预热 matplotlib

    关闭时：
    1. 关闭数据库连接池
    """
    print("=" * 50)
    print("Data Analyst Agent Starting...")
    print("=" * 50)

    validate_settings()
    await db_pool.initialize()

    print("Initializing checkpointer (short-term memory)...")
    try:
        await setup_checkpointer()
        print("Checkpointer initialized successfully!")
        
        # 启动时清理旧的 checkpoint（保留最近7天）
        print("Cleaning up old checkpoints...")
        from utils.checkpoint_cleanup import cleanup_old_checkpoints
        cleanup_result = await cleanup_old_checkpoints(days_to_keep=7, dry_run=False)
        if cleanup_result.get("deleted_checkpoints", 0) > 0:
            print(f"Cleaned up {cleanup_result['deleted_checkpoints']} old checkpoints")
    except Exception as e:
        print(f"Warning: Checkpointer setup failed: {e}")
        print("Short-term memory will use fallback mode.")

    import threading
    def warmup_matplotlib():
        try:
            from tools.viz_tools import warmup_matplotlib as _warmup
            _warmup()
        except Exception as e:
            print(f"Matplotlib warmup failed: {e}")
    
    warmup_thread = threading.Thread(target=warmup_matplotlib, daemon=True)
    warmup_thread.start()

    print("=" * 50)
    print("Service Started!")
    print("Short-term memory enabled: Multi-turn conversations supported!")
    print("=" * 50)

    yield

    print("Shutting down...")
    await close_checkpointer()
    await db_pool.close()
    print("Service stopped.")


app = FastAPI(
    title="Data Analyst Agent",
    description="Natural Language Data Analysis Assistant",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

STATIC_DIR = PROJECT_ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve frontend page"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Data Analyst Agent API", "docs": "/docs"}


def main():
    """Main entry point"""
    settings = get_settings()

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=True
    )


if __name__ == "__main__":
    main()
