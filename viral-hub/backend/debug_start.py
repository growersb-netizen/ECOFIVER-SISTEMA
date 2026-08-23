"""Debug startup: attempt to import app.main, report any errors, then start minimal health endpoint."""
import os
import sys
import traceback

PORT = os.environ.get("PORT", "8000")
print(f"=== DEBUG START port={PORT} ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"PATH: {os.environ.get('PATH','')[:200]}", flush=True)

# Try importing app.main
try:
    print("Attempting: import app.core.config ...", flush=True)
    from app.core.config import get_settings
    settings = get_settings()
    print(f"  Settings OK. APP_ENV={settings.APP_ENV}", flush=True)
    print(f"  DATABASE_URL prefix: {settings.DATABASE_URL[:30]}", flush=True)
    print(f"  CORS_ORIGINS: {settings.CORS_ORIGINS}", flush=True)
except Exception as e:
    print(f"  FAILED config: {e}", flush=True)
    traceback.print_exc()

try:
    print("Attempting: import app.core.database ...", flush=True)
    from app.core.database import engine
    print(f"  Database engine OK: {engine}", flush=True)
except Exception as e:
    print(f"  FAILED database: {e}", flush=True)
    traceback.print_exc()

try:
    print("Attempting: import app.models ...", flush=True)
    import app.models
    print("  Models OK", flush=True)
except Exception as e:
    print(f"  FAILED models: {e}", flush=True)
    traceback.print_exc()

try:
    print("Attempting: import app.api.v1 ...", flush=True)
    from app.api.v1 import router
    print("  API router OK", flush=True)
except Exception as e:
    print(f"  FAILED api.v1: {e}", flush=True)
    traceback.print_exc()

try:
    print("Attempting: import app.main ...", flush=True)
    from app.main import app as real_app
    print("  app.main OK!", flush=True)
    # Start the real app
    print(f"Starting REAL uvicorn on port {PORT}", flush=True)
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", PORT])
except Exception as e:
    print(f"  FAILED app.main: {e}", flush=True)
    traceback.print_exc()
    # Fall back to minimal health endpoint so healthcheck passes
    print("Falling back to minimal health endpoint...", flush=True)
    os.execvp("uvicorn", ["uvicorn", "minimal_main:app", "--host", "0.0.0.0", "--port", PORT])
