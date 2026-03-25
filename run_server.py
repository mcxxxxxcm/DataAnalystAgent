import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("Data Analyst Agent Starting...")
print("=" * 50)

print("\nStep 1: Loading configuration...")
from config.settings import get_settings, validate_settings
settings = get_settings()
print(f"  - API_KEY: {settings.api_key[:10]}...")
print(f"  - BASE_URL: {settings.base_url}")
print(f"  - LLM_MODEL: {settings.llm_model}")
print(f"  - DB: {settings.db_host}:{settings.db_port}/{settings.db_name}")

print("\nStep 2: Loading database module...")
from core.database import db_pool
print("  - Database module loaded")

print("\nStep 3: Loading tools...")
from tools import SQL_TOOLS
print(f"  - {len(SQL_TOOLS)} tools loaded")

print("\nStep 4: Loading middleware...")
from middleware import get_middleware_list
print("  - Middleware loaded")

print("\nStep 5: Creating FastAPI app (agent will be lazy-loaded)...")
from api.main import app
print("  - FastAPI app created")

print("\nStep 6: Starting server...")
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8082)
