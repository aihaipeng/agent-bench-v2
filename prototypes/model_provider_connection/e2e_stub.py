from __future__ import annotations

import asyncio

import uvicorn
from fastapi import FastAPI, Header, HTTPException


app = FastAPI(docs_url=None, redoc_url=None)


@app.get("/")
async def root() -> dict[str, bool]:
    await asyncio.sleep(0.04)
    return {"ok": True}


@app.get("/v1/models")
def models(authorization: str | None = Header(None)) -> dict:
    if authorization != "Bearer demo-key":
        raise HTTPException(401, "invalid key")
    return {
        "object": "list",
        "data": [
            {"id": "deepseek-chat", "owned_by": "demo"},
            {"id": "qwen-max", "owned_by": "demo"},
            {"id": "claude-sonnet", "owned_by": "demo"},
        ],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8025, log_level="warning")
