"""Check all key imports and report failures. Starts uvicorn after."""
import os, sys
PORT = os.environ.get("PORT", "8000")
print(f"Python {sys.version} | PORT={PORT}", flush=True)

packages = [
    ("fastapi", "from fastapi import FastAPI"),
    ("sqlalchemy", "from sqlalchemy.ext.asyncio import create_async_engine"),
    ("asyncpg", "import asyncpg"),
    ("cryptography", "from cryptography.fernet import Fernet"),
    ("celery", "from celery import Celery"),
    ("authlib", "from authlib.integrations.httpx_client import AsyncOAuth2Client"),
    ("sentry_sdk", "import sentry_sdk"),
    ("app.core.config", "from app.core.config import get_settings; get_settings()"),
    ("app.core.database", "from app.core.database import engine"),
    ("app.api.v1", "from app.api.v1 import router"),
    ("app.main", "from app.main import app"),
]

all_ok = True
for name, code in packages:
    try:
        exec(code)
        print(f"  OK: {name}", flush=True)
    except Exception as e:
        print(f"  FAIL: {name} → {type(e).__name__}: {e}", flush=True)
        all_ok = False

print(f"\nAll OK: {all_ok}", flush=True)
if all_ok:
    print(f"Starting uvicorn on port {PORT}...", flush=True)
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", PORT])
else:
    print("Falling back to minimal health endpoint...", flush=True)
    os.execvp("uvicorn", ["uvicorn", "minimal_main:app", "--host", "0.0.0.0", "--port", PORT])
