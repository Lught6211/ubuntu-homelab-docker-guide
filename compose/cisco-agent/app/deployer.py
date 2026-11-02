from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


REPO_DIR = Path(os.getenv("CISCO_DEPLOY_REPO_DIR", "/workspace")).resolve()
REPO_URL = os.getenv(
    "CISCO_DEPLOY_REPO_URL",
    "https://github.com/Lught6211/ubuntu-homelab-docker-guide.git",
)
COMPOSE_FILE = REPO_DIR / "compose/cisco-agent/compose.host-network.yaml"
ENV_FILE = Path(os.getenv("CISCO_DEPLOY_ENV_FILE", "/run/secrets/cisco-agent.env"))
STATE_FILE = Path(os.getenv("CISCO_DEPLOY_STATE_FILE", "/state/status.json"))
TOKEN = os.getenv("CISCO_DEPLOY_TOKEN", "")
if not TOKEN or len(TOKEN) < 32:
    raise RuntimeError("CISCO_DEPLOY_TOKEN must be at least 32 characters")

app = FastAPI(title="CISCO Fixed Homelab Deployer", version="1.0.0", docs_url=None, redoc_url=None)
bearer = HTTPBearer(auto_error=False)
state_lock = threading.Lock()
cache_lock = threading.Lock()
remote_cache: dict[str, Any] = {"checked_at": 0.0, "sha": None}


def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    supplied = credentials.credentials if credentials else ""
    if not supplied or not hmac.compare_digest(supplied, TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid deploy service token")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(value: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    temporary.replace(STATE_FILE)


def command(args: list[str], *, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.getenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": os.getenv("HOME", "/tmp/cisco-deployer"),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(REPO_DIR),
        "DOCKER_HOST": "unix:///var/run/docker.sock",
    }
    try:
        result = subprocess.run(
            args,
            cwd=REPO_DIR,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("A fixed deployment step could not start or timed out") from exc
    if check and result.returncode != 0:
        raise RuntimeError("A fixed deployment step failed")
    return result


def safe_repo_state() -> dict[str, Any]:
    if not REPO_DIR.is_dir() or not (REPO_DIR / ".git").exists():
        raise HTTPException(status_code=503, detail="The managed CISCO guide repository is unavailable")
    origin = command(["git", "remote", "get-url", "origin"]).stdout.strip()
    if origin.rstrip("/") not in {REPO_URL.rstrip("/"), REPO_URL.removesuffix(".git").rstrip("/")}:
        raise HTTPException(status_code=409, detail="The server repository origin does not match the approved public repository")
    branch = command(["git", "branch", "--show-current"]).stdout.strip()
    current = command(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(command(["git", "status", "--porcelain"], check=True).stdout.strip())
    return {"branch": branch, "current_sha": current, "dirty": dirty}


def latest_commit(*, force: bool = False) -> str:
    with cache_lock:
        cached_sha = remote_cache["sha"]
        fresh = time.monotonic() - float(remote_cache["checked_at"]) < 300
        if cached_sha and fresh and not force:
            return str(cached_sha)
    result = command(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/main"],
        timeout=25,
    )
    match = re.match(r"^([a-f0-9]{40})\s+refs/heads/main\s*$", result.stdout.strip())
    if not match:
        raise HTTPException(status_code=503, detail="GitHub did not return the approved main branch")
    with cache_lock:
        remote_cache["checked_at"] = time.monotonic()
        remote_cache["sha"] = match.group(1)
    return match.group(1)


def deployment_snapshot(*, force: bool = False) -> dict[str, Any]:
    repo = safe_repo_state()
    latest = latest_commit(force=force)
    branch_ok = repo["branch"] == "main"
    dirty = repo["dirty"]
    current = repo["current_sha"]
    job = read_state()
    running = job.get("status") == "running"
    return {
        "checked_at": utc_now(),
        "branch": repo["branch"],
        "current_sha": current,
        "latest_sha": latest,
        "update_available": latest != current,
        "repository_dirty": dirty,
        "deploy_allowed": branch_ok and not dirty and not running,
        "blocked_reason": "The deploy checkout has local changes." if dirty else "The deploy checkout is not on main." if not branch_ok else "A deployment is already running." if running else None,
        "job": job or {"status": "idle", "steps": []},
    }


def set_job(job: dict[str, Any]) -> None:
    with state_lock:
        write_state(job)


def mark_step(job: dict[str, Any], name: str, state: str) -> None:
    steps = list(job.get("steps", []))
    existing = next((index for index, item in enumerate(steps) if item.get("name") == name), None)
    record = {"name": name, "status": state}
    if existing is None:
        steps.append(record)
    else:
        steps[existing] = record
    job["steps"] = steps
    job["updated_at"] = utc_now()
    set_job(job)


def run_deployment(job: dict[str, Any]) -> None:
    old_sha = ""
    merged = False
    try:
        repo = safe_repo_state()
        if repo["branch"] != "main" or repo["dirty"]:
            raise RuntimeError("The deploy checkout is not a clean main branch")
        old_sha = repo["current_sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", old_sha):
            raise RuntimeError("The current source revision is invalid")

        mark_step(job, "Check approved GitHub repository", "running")
        command(["git", "fetch", "--quiet", "--no-tags", "origin", "refs/heads/main"], timeout=60)
        new_sha = command(["git", "rev-parse", "FETCH_HEAD"]).stdout.strip()
        if not re.fullmatch(r"[a-f0-9]{40}", new_sha):
            raise RuntimeError("GitHub returned an invalid source revision")
        mark_step(job, "Check approved GitHub repository", "complete")
        if new_sha == old_sha:
            job.update({"status": "succeeded", "message": "CISCO is already on the latest main commit.", "finished_at": utc_now()})
            mark_step(job, "Deploy fixed CISCO services", "skipped")
            set_job(job)
            return
        ancestor = command(["git", "merge-base", "--is-ancestor", old_sha, new_sha], check=False)
        if ancestor.returncode != 0:
            raise RuntimeError("The remote main branch is not a fast-forward update")

        mark_step(job, "Fast-forward approved source", "running")
        command(["git", "merge", "--ff-only", new_sha])
        merged = True
        mark_step(job, "Fast-forward approved source", "complete")

        compose_prefix = [
            "docker", "compose", "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE), "-p", "cisco-agent"
        ]
        mark_step(job, "Validate compose configuration", "running")
        command(compose_prefix + ["config", "--quiet"], timeout=45)
        mark_step(job, "Validate compose configuration", "complete")

        mark_step(job, "Rebuild and restart CISCO services", "running")
        command(
            compose_prefix + ["up", "-d", "--build", "cisco-docker-guard", "cisco-homelab-agent"],
            timeout=420,
        )
        mark_step(job, "Rebuild and restart CISCO services", "complete")
        job.update({"status": "succeeded", "deployed_sha": new_sha, "message": "CISCO server agent update deployed.", "finished_at": utc_now()})
        set_job(job)
    except Exception:
        rolled_back = False
        if merged and old_sha:
            try:
                command(["git", "reset", "--hard", old_sha])
                compose_prefix = [
                    "docker", "compose", "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE), "-p", "cisco-agent"
                ]
                command(compose_prefix + ["up", "-d", "--build", "cisco-docker-guard", "cisco-homelab-agent"], timeout=420)
                rolled_back = True
            except Exception:
                rolled_back = False
        job.update({
            "status": "failed",
            "message": "Deployment failed; the previous CISCO version was restored." if rolled_back else "Deployment failed. Check the server deployment status before retrying.",
            "rolled_back": rolled_back,
            "finished_at": utc_now(),
        })
        for step in job.get("steps", []):
            if step.get("status") == "running":
                step["status"] = "failed"
        set_job(job)


@app.on_event("startup")
async def recover_interrupted_job() -> None:
    job = read_state()
    if job.get("status") == "running":
        job.update({"status": "failed", "message": "The deploy service restarted during the last deployment. Check service health before retrying.", "finished_at": utc_now()})
        write_state(job)


@app.get("/status")
async def status_snapshot(force: bool = Query(False), _: None = Depends(require_token)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(deployment_snapshot, force=force)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The CISCO update status could not be checked") from exc


@app.post("/deploy", status_code=202)
async def start_deploy(_: None = Depends(require_token)) -> dict[str, Any]:
    with state_lock:
        existing = read_state()
        if existing.get("status") == "running":
            raise HTTPException(status_code=409, detail="A deployment is already running")
        try:
            snapshot = await asyncio.to_thread(deployment_snapshot, force=True)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="The CISCO update status could not be checked") from exc
        if not snapshot["deploy_allowed"]:
            raise HTTPException(status_code=409, detail=snapshot["blocked_reason"] or "Deployment is not allowed")
        if not snapshot["update_available"]:
            raise HTTPException(status_code=409, detail="CISCO is already on the latest main commit")
        job = {
            "id": str(uuid.uuid4()),
            "status": "running",
            "message": "Updating only the CISCO homelab agent and Docker guard.",
            "requested_at": utc_now(),
            "updated_at": utc_now(),
            "steps": [],
        }
        write_state(job)
    threading.Thread(target=run_deployment, args=(job,), name="cisco-fixed-deploy", daemon=True).start()
    return {"job": job}
