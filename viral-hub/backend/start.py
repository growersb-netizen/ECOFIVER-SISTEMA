"""Startup script: wait for postgres, run migrations, start uvicorn."""
import os
import sys
import time
import subprocess

PORT = os.environ.get("PORT", "8000")
DB_SYNC = os.environ.get("DATABASE_SYNC_URL", "")

print(f"=== Viral Hub API starting on port {PORT} ===", flush=True)
print(f"DATABASE_SYNC_URL prefix: {DB_SYNC[:40]}", flush=True)

# Wait for Postgres (up to 60 seconds)
print("Waiting for Postgres...", flush=True)
for attempt in range(60):
    try:
        import psycopg2
        conn = psycopg2.connect(DB_SYNC, connect_timeout=2)
        conn.close()
        print(f"Postgres ready after {attempt+1} attempt(s)", flush=True)
        break
    except Exception as e:
        if attempt % 5 == 0:
            print(f"  attempt {attempt+1}/60: {e}", flush=True)
        time.sleep(1)
else:
    print("WARNING: Postgres not reachable after 60s — continuing anyway", flush=True)

# Run alembic migrations
print("Running: alembic upgrade head", flush=True)
result = subprocess.run(["alembic", "upgrade", "head"], capture_output=False)
if result.returncode != 0:
    print(f"WARNING: alembic exited with code {result.returncode} — starting anyway", flush=True)
else:
    print("Migrations OK", flush=True)

# Start uvicorn
print(f"Starting uvicorn on 0.0.0.0:{PORT}", flush=True)
os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", PORT])
