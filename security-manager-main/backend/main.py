from fastapi import FastAPI, Request
from worker import celery_app

from tortoise.contrib.fastapi import register_tortoise
from fastapi.middleware.cors import CORSMiddleware
import os
import hmac
import hashlib
import json
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "postgres://guardian:password@db:5432/security_guardian")


app = FastAPI(title="Security Guardian API")

# Ensure CORS middleware is added before any routes or DB registration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://frontend:5173",
        "http://localhost:8000",
        "http://backend:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_tortoise(
    app,
    db_url=DATABASE_URL,
    modules={"models": ["app.models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)

@app.get("/")
def read_root():
    return {"status": "Security Guardian is Active", "version": "1.0.0"}

@app.get("/health")
def health_check():
    return {"db": "connected", "redis": "connected"}

@app.post("/scan")
async def trigger_scan(repo_url: str, target_url: str = None, github_token: str = None):
    from worker import execute_scan
    
    # Derive clone_url and repo_full_name from the repo_url
    clone_url = repo_url if repo_url.endswith(".git") else repo_url + ".git"
    
    # Extract "owner/repo" from URL like "https://github.com/owner/repo"
    repo_full_name = ""
    if "github.com" in repo_url:
        parts = repo_url.rstrip("/").rstrip(".git").split("github.com/")
        if len(parts) > 1:
            repo_full_name = parts[1]
    
    task = execute_scan.delay(
        repo_url,
        clone_url=clone_url,
        repo_full_name=repo_full_name,
        target_url=target_url or "",
        github_token=github_token or ""
    )
    return {"task_id": task.id, "status": "queued", "repo_url": repo_url, "target_url": target_url}

@app.get("/scans")
async def list_scans():
    from app.models import ScanResult, ScanLog
    scans = await ScanResult.all().prefetch_related("repo_config").order_by("-created_at")
    results = []
    for s in scans:
        # Get total tokens used for this scan
        logs = await ScanLog.filter(scan_result_id=s.id)
        tokens_input = sum(l.tokens_input for l in logs)
        tokens_output = sum(l.tokens_output for l in logs)
        
        results.append({
            "id": s.id,
            "repo": s.repo_config.url,
            "status": s.status,
            "created_at": s.created_at,
            "ended_at": s.ended_at,
            "tokens_used": tokens_input + tokens_output,
        })
    return results


@app.get("/scans/{scan_id}/logs")
async def get_scan_logs(scan_id: int):
    """Returns phase-wise token usage breakdown for a scan."""
    from app.models import ScanLog
    logs = await ScanLog.filter(scan_result_id=scan_id).order_by("timestamp")
    return [
        {
            "step": l.step,
            "tokens_input": l.tokens_input,
            "tokens_output": l.tokens_output,
            "tokens_total": l.tokens_input + l.tokens_output,
            "model": l.model_name or "—",
            "message": l.message or "",
            "timestamp": l.timestamp,
        }
        for l in logs
    ]


@app.get("/scans/{scan_id}/report")
async def get_scan_report(scan_id: int):
    """Returns the full pipeline report for a scan."""
    from app.models import ScanResult
    scan = await ScanResult.get_or_none(id=scan_id).prefetch_related("repo_config")
    if not scan:
        return {"error": "Scan not found"}
    return {
        "id": scan.id,
        "repo": scan.repo_config.url,
        "status": scan.status,
        "created_at": str(scan.created_at),
        "report": scan.report_data or {},
    }

@app.post("/scans/{scan_id}/cancel")
async def cancel_scan(scan_id: int):
    """Cancels a running or queued scan."""
    from app.models import ScanResult
    scan = await ScanResult.get_or_none(id=scan_id)
    
    if not scan:
        return {"error": "Scan not found"}
        
    if scan.status in ["finished", "failed", "cancelled"]:
        return {"msg": f"Scan is already {scan.status}"}
        
    if scan.celery_task_id:
        from worker import celery_app
        # Revoke the task and terminate if it's already running
        celery_app.control.revoke(scan.celery_task_id, terminate=True, signal="SIGKILL")
        
    scan.status = "cancelled"
    scan.ended_at = datetime.now(timezone.utc)
    
    # Update report data to reflect the cancellation reason clearly
    report = scan.report_data or {}
    report["error"] = "Scan was cancelled by the user."
    scan.report_data = report
    
    await scan.save()
    return {"status": "cancelled", "scan_id": scan.id}



# ─── Config Endpoints ───────────────────────────────────────────────

@app.get("/config")
async def get_config():
    """Returns all system config entries. Secrets are masked."""
    from app.models import SystemConfig
    configs = await SystemConfig.all()
    return [
        {
            "key": c.key,
            "value": (c.value[:4] + "*" * (len(c.value) - 4)) if c.is_secret and len(c.value) > 4 else ("****" if c.is_secret else c.value),
            "is_secret": c.is_secret,
        }
        for c in configs
    ]


@app.post("/config")
async def set_config(key: str, value: str, is_secret: bool = False):
    """Create or update a system config entry."""
    from app.models import SystemConfig
    config, created = await SystemConfig.get_or_create(key=key, defaults={"value": value, "is_secret": is_secret})
    if not created:
        config.value = value
        config.is_secret = is_secret
        await config.save()
    return {"key": config.key, "status": "created" if created else "updated"}


# ─── Webhook Helpers ────────────────────────────────────────────────

def verify_github_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook/github")
async def github_webhook(request: Request):
    """
    Receives GitHub webhook events.
    Triggers a security scan when a Pull Request is opened or updated.
    """
    # Read webhook secret from DB (SystemConfig), fall back to env
    from app.models import SystemConfig
    try:
        config = await SystemConfig.get(key="GITHUB_WEBHOOK_SECRET")
        webhook_secret = config.value
    except Exception:
        webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    
    # 1. Read raw body for signature verification
    body = await request.body()
    
    # 2. Verify signature (skip if no secret configured — for dev convenience)
    signature = request.headers.get("X-Hub-Signature-256", "")
    if webhook_secret and webhook_secret != "your-webhook-secret-here":
        if not verify_github_signature(body, signature, webhook_secret):
            return {"error": "Invalid signature"}, 403
    
    # 3. Parse event
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)
    
    # 4. Handle ping (GitHub sends this when webhook is first registered)
    if event_type == "ping":
        return {"msg": "pong", "zen": payload.get("zen")}
    
    # 5. Handle pull_request events
    if event_type == "pull_request":
        action = payload.get("action", "")
        
        # Only trigger on opened, synchronize (new commits pushed), or reopened
        if action not in ["opened", "synchronize", "reopened"]:
            return {"msg": f"Ignoring PR action: {action}"}
        
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        
        repo_url = repo.get("html_url", "")
        clone_url = repo.get("clone_url", "")
        pr_number = pr.get("number", 0)
        commit_sha = pr.get("head", {}).get("sha", "HEAD")
        pr_branch = pr.get("head", {}).get("ref", "main")
        repo_full_name = repo.get("full_name", "")  # e.g. "owner/repo"
        
        print(f"Webhook: PR #{pr_number} ({action}) on {repo_full_name} — sha: {commit_sha}")
        
        from worker import execute_scan
        task = execute_scan.delay(
            repo_url,
            pr_number=pr_number,
            commit_sha=commit_sha,
            clone_url=clone_url,
            pr_branch=pr_branch,
            repo_full_name=repo_full_name
        )
        
        return {
            "task_id": task.id,
            "status": "queued",
            "event": "pull_request",
            "action": action,
            "pr_number": pr_number
        }
    
    return {"msg": f"Ignoring event: {event_type}"}
