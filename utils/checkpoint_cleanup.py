"""
Checkpoint 清理工具

用于清理旧的 checkpoint 数据，减少数据库存储
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional


async def cleanup_old_checkpoints(
    days_to_keep: int = 7,
    dry_run: bool = False
) -> dict:
    """
    清理旧的 checkpoint 数据
    
    参数:
        days_to_keep: 保留最近多少天的数据
        dry_run: 如果为 True，只统计不删除
    
    返回:
        清理结果统计
    """
    from config.settings import get_settings
    from core.database import db_pool
    
    settings = get_settings()
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    stats = {
        "cutoff_date": cutoff_date.isoformat(),
        "dry_run": dry_run,
        "deleted_checkpoints": 0,
        "deleted_writes": 0,
        "deleted_blobs": 0,
        "remaining_checkpoints": 0
    }
    
    try:
        # 统计要删除的记录数
        count_query = """
        SELECT COUNT(*) as count FROM checkpoints 
        WHERE created_at < $1
        """
        result = await db_pool.fetchrow(count_query, cutoff_date)
        stats["deleted_checkpoints"] = result["count"] if result else 0
        
        # 统计剩余记录数
        remaining_query = "SELECT COUNT(*) as count FROM checkpoints"
        result = await db_pool.fetchrow(remaining_query)
        stats["remaining_checkpoints"] = result["count"] if result else 0
        
        if not dry_run and stats["deleted_checkpoints"] > 0:
            # 删除旧的 checkpoint_writes
            delete_writes = """
            DELETE FROM checkpoint_writes
            WHERE checkpoint_id IN (
                SELECT checkpoint_id FROM checkpoints 
                WHERE created_at < $1
            )
            """
            await db_pool.execute(delete_writes, cutoff_date)
            
            # 删除旧的 checkpoint_blobs
            delete_blobs = """
            DELETE FROM checkpoint_blobs
            WHERE thread_id IN (
                SELECT DISTINCT thread_id FROM checkpoints 
                WHERE created_at < $1
            )
            """
            await db_pool.execute(delete_blobs, cutoff_date)
            
            # 删除旧的 checkpoints
            delete_checkpoints = """
            DELETE FROM checkpoints WHERE created_at < $1
            """
            result = await db_pool.execute(delete_checkpoints, cutoff_date)
            stats["deleted_checkpoints"] = int(result.split()[-1]) if result else 0
            
        return stats
        
    except Exception as e:
        return {
            **stats,
            "error": str(e)
        }


async def cleanup_orphaned_checkpoints(dry_run: bool = False) -> dict:
    """
    清理孤立的 checkpoint 数据（没有对应 thread 的）
    
    参数:
        dry_run: 如果为 True，只统计不删除
    
    返回:
        清理结果统计
    """
    from core.database import db_pool
    
    stats = {
        "dry_run": dry_run,
        "orphaned_threads": 0
    }
    
    try:
        # 查找孤立的 thread_id
        orphan_query = """
        SELECT DISTINCT c.thread_id 
        FROM checkpoints c
        LEFT JOIN conversations conv ON c.thread_id = conv.thread_id
        WHERE conv.thread_id IS NULL
        """
        rows = await db_pool.fetch(orphan_query)
        orphaned_threads = [r["thread_id"] for r in rows]
        stats["orphaned_threads"] = len(orphaned_threads)
        
        if not dry_run and orphaned_threads:
            # 删除孤立的数据
            for thread_id in orphaned_threads:
                await db_pool.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = $1",
                    thread_id
                )
                await db_pool.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = $1",
                    thread_id
                )
                await db_pool.execute(
                    "DELETE FROM checkpoints WHERE thread_id = $1",
                    thread_id
                )
        
        return stats
        
    except Exception as e:
        return {
            **stats,
            "error": str(e)
        }


async def get_checkpoint_stats() -> dict:
    """
    获取 checkpoint 统计信息
    """
    from core.database import db_pool
    
    try:
        stats = {}
        
        # 各表记录数
        tables = ["checkpoints", "checkpoint_writes", "checkpoint_blobs"]
        for table in tables:
            result = await db_pool.fetchrow(f"SELECT COUNT(*) as count FROM {table}")
            stats[f"{table}_count"] = result["count"] if result else 0
        
        # 按日期统计
        date_query = """
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM checkpoints
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 7
        """
        rows = await db_pool.fetch(date_query)
        stats["by_date"] = [{"date": str(r["date"]), "count": r["count"]} for r in rows]
        
        # 最旧和最新记录
        oldest = await db_pool.fetchrow(
            "SELECT MIN(created_at) as oldest FROM checkpoints"
        )
        newest = await db_pool.fetchrow(
            "SELECT MAX(created_at) as newest FROM checkpoints"
        )
        stats["oldest_checkpoint"] = str(oldest["oldest"]) if oldest and oldest["oldest"] else None
        stats["newest_checkpoint"] = str(newest["newest"]) if newest and newest["newest"] else None
        
        return stats
        
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    async def main():
        print("=" * 50)
        print("Checkpoint Statistics")
        print("=" * 50)
        stats = await get_checkpoint_stats()
        for key, value in stats.items():
            print(f"{key}: {value}")
        
        print("\n" + "=" * 50)
        print("Cleaning up checkpoints older than 7 days...")
        print("=" * 50)
        result = await cleanup_old_checkpoints(days_to_keep=7, dry_run=True)
        print(f"Would delete: {result}")
    
    asyncio.run(main())
