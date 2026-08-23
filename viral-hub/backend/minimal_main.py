"""Minimal FastAPI app for Railway healthcheck debugging."""
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok", "port": os.environ.get("PORT", "unknown")}
