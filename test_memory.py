"""
测试短期记忆功能

测试多轮对话上下文保持
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx


async def test_multi_turn_conversation():
    """测试多轮对话"""
    base_url = "http://localhost:8085/api"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        thread_id = None
        
        queries = [
            "查询所有表",
            "获取 users 表的结构",
        ]
        
        for i, query in enumerate(queries):
            print(f"\n{'='*50}")
            print(f"第 {i+1} 轮对话")
            print(f"用户: {query}")
            print(f"{'='*50}")
            
            payload = {"query": query}
            if thread_id:
                payload["thread_id"] = thread_id
            
            try:
                response = await client.post(
                    f"{base_url}/query",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    thread_id = data.get("thread_id")
                    print(f"会话ID: {thread_id}")
                    
                    if data.get("success"):
                        print(f"Agent: {data.get('message', '成功')}")
                    elif data.get("requires_approval"):
                        print(f"需要审核: {data.get('approval_request')}")
                    else:
                        print(f"错误: {data.get('error')}")
                else:
                    print(f"HTTP错误: {response.status_code}")
                    print(f"响应: {response.text}")
                    
            except Exception as e:
                print(f"请求失败: {e}")
        
        print(f"\n{'='*50}")
        print("测试完成!")
        print(f"最终会话ID: {thread_id}")
        print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(test_multi_turn_conversation())
