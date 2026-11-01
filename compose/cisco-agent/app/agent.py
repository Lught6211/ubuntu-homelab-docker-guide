from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
import psutil
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


def json_env(name: str, default: Any) -> Any:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must contain valid JSON") from exc


TOKEN = os.getenv("CISCO_API_TOKEN", "")
if TOKEN and len(TOKEN) < 32:
    raise RuntimeError("CISCO_API_TOKEN must be at least 32 characters")
TAILSCALE_ALLOWED_USERS = {
    user.strip().lower()
    for user in os.getenv("CISCO_TAILSCALE_ALLOWED_USERS", "").split(",")
    if user.strip()
}
if not TOKEN and not TAILSCALE_ALLOWED_USERS:
    raise RuntimeError("Configure CISCO_API_TOKEN or CISCO_TAILSCALE_ALLOWED_USERS")

SERVER_LABEL = os.getenv("CISCO_SERVER_LABEL", "HOMELAB NODE")
MANAGED_SERVICES: dict[str, str] = json_env(
    "CISCO_MANAGED_SERVICES", {"jellyfin": "jellyfin", "caddy": "caddy"}
)
MONITORED_SITES: list[dict[str, str]] = json_env("CISCO_MONITORED_SITES", [])
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CISCO_ALLOWED_ORIGINS", "https://project-cisco.vercel.app,http://localhost:3000"
    ).split(",")
    if origin.strip()
]
QBITTORRENT_URL = os.getenv("QBITTORRENT_URL", "").rstrip("/")
QBITTORRENT_USERNAME = os.getenv("QBITTORRENT_USERNAME", "")
QBITTORRENT_PASSWORD = os.getenv("QBITTORRENT_PASSWORD", "")
DOCKER_GUARD_URL = "http://127.0.0.1:2375"

app = FastAPI(title="CISCO Homelab Agent", version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
bearer = HTTPBearer(auto_error=False)


def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    tailscale_user = request.headers.get("Tailscale-User-Login", "").strip().lower()
    if tailscale_user and tailscale_user in TAILSCALE_ALLOWED_USERS:
        return
    supplied = credentials.credentials if credentials else ""
    if not TOKEN or not supplied or not hmac.compare_digest(supplied, TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CISCO server token")


@app.get("/health")
async def health() -> dict[str, bool]:
    # Deliberately public but contains no host identity, configuration, or metrics.
    return {"ok": True}


async def docker_request(method: str, path: str) -> httpx.Response:
    try:
        async with httpx.AsyncClient(base_url=DOCKER_GUARD_URL, timeout=4.0, trust_env=False) as client:
            return await client.request(method, path)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Docker monitor is unavailable") from exc


def read_host_metrics() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "label": SERVER_LABEL,
        "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "memory": {
            "percent": round(memory.percent, 1),
            "used_bytes": memory.used,
            "total_bytes": memory.total,
        },
        "filesystem": {
            "percent": round(disk.percent, 1),
            "used_bytes": disk.used,
            "total_bytes": disk.total,
        },
    }


async def get_services() -> list[dict[str, Any]]:
    response = await docker_request("GET", "/containers/json?all=1")
    if response.is_error:
        raise HTTPException(status_code=503, detail="Docker monitor could not list containers")
    containers = response.json()
    managed_by_container = {container: alias for alias, container in MANAGED_SERVICES.items()}
    services = []
    for item in containers:
        names = [name.lstrip("/") for name in item.get("Names", [])]
        primary = names[0] if names else item.get("Id", "")[:12]
        alias = managed_by_container.get(primary)
        services.append(
            {
                "id": item.get("Id", "")[:12],
                "name": primary,
                "label": alias.replace("-", " ").title() if alias else primary.replace("-", " ").title(),
                "state": item.get("State", "unknown"),
                "status": item.get("Status", ""),
                "controls_allowed": alias is not None,
                "managed_id": alias,
            }
        )
    return services


async def get_sites() -> list[dict[str, Any]]:
    async def check(site: dict[str, str]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, trust_env=False) as client:
                response = await client.get(site["url"])
            return {
                "id": site["id"],
                "name": site.get("name", site["id"]),
                "url": site["url"],
                "status": "online" if response.status_code < 500 else "degraded",
                "http_status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
        except (httpx.HTTPError, KeyError):
            return {
                "id": site.get("id", "site"),
                "name": site.get("name", site.get("id", "Site")),
                "url": site.get("url", ""),
                "status": "offline",
                "http_status": None,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }

    return await asyncio.gather(*(check(site) for site in MONITORED_SITES[:30]))


async def get_downloads() -> dict[str, Any]:
    if not (QBITTORRENT_URL and QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD):
        return {"configured": False, "items": []}
    try:
        async with httpx.AsyncClient(base_url=QBITTORRENT_URL, timeout=5.0, trust_env=False) as client:
            login = await client.post(
                "/api/v2/auth/login",
                data={"username": QBITTORRENT_USERNAME, "password": QBITTORRENT_PASSWORD},
                headers={"Referer": QBITTORRENT_URL + "/", "Origin": QBITTORRENT_URL},
            )
            if login.is_error or login.text.strip() != "Ok.":
                return {"configured": True, "error": "qBittorrent rejected its saved credentials", "items": []}
            response = await client.get("/api/v2/torrents/info")
            response.raise_for_status()
            items = response.json()
    except httpx.HTTPError:
        return {"configured": True, "error": "qBittorrent is unreachable", "items": []}
    return {
        "configured": True,
        "items": [
            {
                "hash": item.get("hash", ""),
                "name": item.get("name", "Download"),
                "progress": round(float(item.get("progress", 0)) * 100, 1),
                "download_speed": int(item.get("dlspeed", 0)),
                "upload_speed": int(item.get("upspeed", 0)),
                "eta_seconds": int(item.get("eta", 0)) if int(item.get("eta", 0)) >= 0 else None,
                "state": item.get("state", "unknown"),
                "paused": item.get("state", "").lower() in {"pauseddl", "pausedup", "stoppeddl", "stoppedup"},
            }
            for item in items[:100]
        ],
    }


@app.get("/api/cisco/overview")
async def overview(_: None = Depends(require_token)) -> dict[str, Any]:
    try:
        services, sites, downloads = await asyncio.gather(get_services(), get_sites(), get_downloads())
    except HTTPException:
        raise
    except Exception as exc:  # Keep one unavailable integration from crashing the status response.
        raise HTTPException(status_code=503, detail="The server status could not be collected") from exc
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "server": await asyncio.to_thread(read_host_metrics),
        "services": services,
        "sites": sites,
        "downloads": downloads,
    }


@app.post("/api/cisco/services/{service_id}/{action}")
async def control_service(service_id: str, action: str, _: None = Depends(require_token)) -> dict[str, str]:
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=404, detail="Only start, stop, and restart are available")
    container = MANAGED_SERVICES.get(service_id)
    if not container:
        raise HTTPException(status_code=404, detail="This service is not in the restart allowlist")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container):
        raise HTTPException(status_code=500, detail="The configured service mapping is invalid")
    listing = await docker_request("GET", "/containers/json?all=1")
    if listing.is_error:
        raise HTTPException(status_code=503, detail="Docker monitor could not find the service")
    target = next(
        (
            item
            for item in listing.json()
            if any(name.lstrip("/") == container for name in item.get("Names", []))
        ),
        None,
    )
    if not target:
        raise HTTPException(status_code=404, detail="The configured container is not present")
    container_id = quote(target.get("Id", ""), safe="")
    query = "?t=10" if action in {"stop", "restart"} else ""
    result = await docker_request("POST", f"/containers/{container_id}/{action}{query}")
    if result.is_error:
        raise HTTPException(status_code=502, detail=f"Docker could not {action} the service")
    return {"status": action, "service": service_id}


@app.post("/api/cisco/downloads/{download_hash}/{action}")
async def control_download(
    download_hash: str, action: str, _: None = Depends(require_token)
) -> dict[str, str]:
    if action not in {"pause", "resume"}:
        raise HTTPException(status_code=404, detail="Only pause and resume are available")
    if not re.fullmatch(r"[a-fA-F0-9]{40,64}", download_hash):
        raise HTTPException(status_code=400, detail="Invalid download identifier")
    if not (QBITTORRENT_URL and QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD):
        raise HTTPException(status_code=503, detail="qBittorrent control is not configured")
    endpoint = "/api/v2/torrents/stop" if action == "pause" else "/api/v2/torrents/start"
    try:
        async with httpx.AsyncClient(base_url=QBITTORRENT_URL, timeout=5.0, trust_env=False) as client:
            login = await client.post(
                "/api/v2/auth/login",
                data={"username": QBITTORRENT_USERNAME, "password": QBITTORRENT_PASSWORD},
                headers={"Referer": QBITTORRENT_URL + "/", "Origin": QBITTORRENT_URL},
            )
            if login.is_error or login.text.strip() != "Ok.":
                raise HTTPException(status_code=502, detail="qBittorrent rejected its saved credentials")
            response = await client.post(
                endpoint,
                data={"hashes": download_hash},
                headers={"Referer": QBITTORRENT_URL + "/", "Origin": QBITTORRENT_URL},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="qBittorrent could not update this download") from exc
    return {"status": action, "download": download_hash}
