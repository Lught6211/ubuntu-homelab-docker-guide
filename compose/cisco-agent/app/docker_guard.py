from __future__ import annotations

import json
import os
import re
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


def configured_services() -> set[str]:
    raw = os.getenv("CISCO_MANAGED_SERVICES", "").strip()
    if not raw:
        return {"jellyfin", "caddy"}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("CISCO_MANAGED_SERVICES must contain valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("CISCO_MANAGED_SERVICES must be a JSON object")
    return {item for item in value.values() if isinstance(item, str)}


ALLOWED_CONTAINERS = configured_services()
DOCKER_SOCKET = "/var/run/docker.sock"
app = FastAPI(docs_url=None, redoc_url=None)


async def docker(method: str, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        base_url="http://docker",
        transport=httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET),
        timeout=5,
        trust_env=False,
    ) as client:
        return await client.request(method, path)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def allowlisted_docker_api(path: str, request: Request) -> Response:
    method = request.method.upper()
    target = "/" + path
    query = request.url.query

    if method == "GET" and target == "/containers/json" and set(parse_qs(query)).issubset({"all", "limit", "since", "before", "size", "filters"}):
        response = await docker("GET", target + ("?" + query if query else ""))
        return Response(content=response.content, status_code=response.status_code, media_type=response.headers.get("content-type"))

    operation = re.fullmatch(r"/containers/([a-fA-F0-9]{12,64})/(start|stop|restart)", target)
    allowed_query = {"t"} if operation and operation.group(2) in {"stop", "restart"} else set()
    if method == "POST" and operation and set(parse_qs(query)).issubset(allowed_query):
        listing = await docker("GET", "/containers/json?all=1")
        if listing.is_error:
            return JSONResponse({"detail": "Docker unavailable"}, status_code=503)
        container_id = operation.group(1).lower()
        permitted = any(
            item.get("Id", "").lower().startswith(container_id)
            and any(name.lstrip("/") in ALLOWED_CONTAINERS for name in item.get("Names", []))
            for item in listing.json()
        )
        if not permitted:
            return JSONResponse({"detail": "Container is outside the restart allowlist"}, status_code=403)
        response = await docker("POST", target + ("?" + query if query else ""))
        return Response(content=response.content, status_code=response.status_code, media_type=response.headers.get("content-type"))

    return JSONResponse({"detail": "Docker operation is not allowed"}, status_code=403)
