"""
Data Analyst Agent 入口文件

启动方式：
    python main.py

或使用 uvicorn：
    uvicorn api.main:app --host 0.0.0.0 --port 8080
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.main import main

if __name__ == "__main__":
    main()
