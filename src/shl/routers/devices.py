"""Device registration endpoints for push notifications."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.shl.store import register_device, unregister_device


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/devices")
    def device_register(request_body: Dict[str, Any]) -> Dict[str, Any]:
        fcm_token = request_body.get("fcm_token")
        if not fcm_token or not isinstance(fcm_token, str):
            raise HTTPException(status_code=400, detail="fcm_token is required")
        platform = request_body.get("platform", "android")
        device_id = register_device(cache_dir, fcm_token, platform)
        return {"device_id": device_id, "status": "registered"}

    @router.delete("/devices")
    def device_unregister(request_body: Dict[str, Any]) -> Dict[str, Any]:
        fcm_token = request_body.get("fcm_token")
        if not fcm_token or not isinstance(fcm_token, str):
            raise HTTPException(status_code=400, detail="fcm_token is required")
        removed = unregister_device(cache_dir, fcm_token)
        if not removed:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"status": "unregistered"}

    return router
