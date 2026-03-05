"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.auth.router import router as auth_router
from app.config import settings
from app.db import create_tables
from app.tasks.polling import poll_rate_limits_loop, poll_usage_costs_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()

    # Start background polling tasks
    rate_task = asyncio.create_task(poll_rate_limits_loop())
    usage_task = asyncio.create_task(poll_usage_costs_loop())

    try:
        yield
    finally:
        rate_task.cancel()
        usage_task.cancel()
        try:
            await rate_task
        except asyncio.CancelledError:
            pass
        try:
            await usage_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="TokenStats", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
