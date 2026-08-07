"""FastAPI application factory.

Creates the app, adds middleware, mounts static files, and includes routers.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.shl.routers import devices, games, health, players, schedule, standings, teams

# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-IP)
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Simple sliding-window rate limiter keyed by client IP."""

    def __init__(self, requests_per_minute: int = 60) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60.0
        self._hits: Dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = self._hits[client_ip]
        # Prune expired entries.
        self._hits[client_ip] = [t for t in hits if t > window_start]
        if len(self._hits[client_ip]) >= self.requests_per_minute:
            return False
        self._hits[client_ip].append(now)
        return True


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def create_app(cache_dir: Path) -> FastAPI:
    app = FastAPI(
        title="SHL Data API",
        version="0.1.0",
        description="Read-only API over persisted SHL schedule, game metadata, and standings data.",
    )

    # CORS — allowed origins configurable via env var (comma-separated).
    # Defaults to permissive for development; set SHL_CORS_ORIGINS in production.
    allowed_origins = os.environ.get("SHL_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # Static file mount for player portraits.
    portraits_dir = cache_dir / "portraits"
    portraits_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/portraits", StaticFiles(directory=str(portraits_dir)), name="portraits")

    # Rate limiting.
    rate_limit = int(os.environ.get("SHL_RATE_LIMIT_PER_MINUTE", "60"))
    limiter = _RateLimiter(requests_per_minute=rate_limit)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Skip rate limiting for health checks.
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(client_ip):
            logger.warning("rate_limited client_ip=%s path=%s", client_ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
            )
        return await call_next(request)

    # ------------------------------------------------------------------
    # Include routers
    # ------------------------------------------------------------------
    app.include_router(health.create_router(cache_dir))
    app.include_router(devices.create_router(cache_dir))
    app.include_router(schedule.create_router(cache_dir))
    app.include_router(standings.create_router(cache_dir))
    app.include_router(players.create_router(cache_dir))
    app.include_router(teams.create_router(cache_dir))
    app.include_router(games.create_router(cache_dir))

    return app
