from celery import Celery
import os
import requests
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "guardian_worker",
    broker=redis_url,
    backend=redis_url
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def set_commit_status(repo_full_name: str, commit_sha: str, state: str, description: str, github_token: str = "", target_url: str = ""):
    """Post a commit status to GitHub (pending, success, failure, error)."""
    if not github_token:
        print(f"CommitStatus: Skipping (no GitHub token provided). State: {state}")
        return
    
    api_url = f"https://api.github.com/repos/{repo_full_name}/statuses/{commit_sha}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "state": state,
        "description": description[:140],
        "context": "security-guardian",
    }
    if target_url:
        payload["target_url"] = target_url
    
    try:
        resp = requests.post(api_url, json=payload, headers=headers)
        if resp.status_code in [200, 201]:
            print(f"CommitStatus: Set '{state}' on {repo_full_name}@{commit_sha[:7]}")
        else:
            print(f"CommitStatus: Failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"CommitStatus: Error posting status: {e}")


def clone_repo(clone_url: str, branch: str = "main", token: str = "") -> str:
    """Shallow clone a repo into a temp directory. Returns the path."""
    tmp_dir = tempfile.mkdtemp(prefix="scan-")
    
    # Inject token into clone URL for private repos
    if token and "github.com" in clone_url:
        clone_url = clone_url.replace("https://", f"https://{token}@")
    
    cmd = ["git", "clone", "--depth", "1", "--branch", branch, clone_url, tmp_dir]
    print(f"Cloning: {clone_url} (branch: {branch}) → {tmp_dir}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # If branch clone fails, try default branch
        print(f"Clone failed for branch '{branch}', trying default branch...")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir = tempfile.mkdtemp(prefix="scan-")
        cmd = ["git", "clone", "--depth", "1", clone_url, tmp_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr}")
    
    print(f"Cloned successfully to {tmp_dir}")
    return tmp_dir


@celery_app.task(bind=True)
def execute_scan(self, repo_url: str, **kwargs):
    import asyncio
    from app.flows.guardian_flow import GuardianFlow
    from app.db import init_db, close_db
    from app.models import ScanResult, ScanLog, RepoConfig
    
    # Extract optional PR metadata
    pr_number = kwargs.get("pr_number", 0)
    commit_sha = kwargs.get("commit_sha", "HEAD")
    clone_url = kwargs.get("clone_url", "")
    pr_branch = kwargs.get("pr_branch", "main")
    repo_full_name = kwargs.get("repo_full_name", "")
    target_url = kwargs.get("target_url", "")
    github_token = kwargs.get("github_token", "")
    
    async def run_flow():
        repo_path = None
        scan = None  # Initialize for crash-safe updates
        
        print(f"Starting scan for {repo_url}")
        if pr_number:
            print(f"  PR #{pr_number}, SHA: {commit_sha}, Branch: {pr_branch}")
        
        # Require GitHub token — no fallback to env
        if not github_token:
            print("ERROR: No GitHub token provided. Cannot clone private repos or post commit statuses.")
            print("Please provide a GitHub token in the UI when triggering a scan.")
        
        # Set commit status to pending
        if repo_full_name and commit_sha != "HEAD" and github_token:
            set_commit_status(repo_full_name, commit_sha, "pending", "Security scan in progress...", github_token)
        
        # Initialize DB
        await init_db()
        
        try:
            # Clone the repo if we have a clone URL
            if clone_url:
                repo_path = clone_repo(clone_url, pr_branch, github_token)
            
            # Create/Get RepoConfig (store the token for this repo)
            config, _ = await RepoConfig.get_or_create(url=repo_url)
            if github_token:
                config.access_token = github_token
                await config.save()
            
            # Create ScanResult - PENDING
            scan = await ScanResult.create(
                repo_config=config, 
                pr_number=pr_number or 1,
                commit_sha=commit_sha,
                status="pending",
                celery_task_id=self.request.id
            )
            
            async def on_node_complete(state: dict):
                # Check DB for cancellation mid-flight to gracefully abort if Cancel requested
                db_scan = await ScanResult.get_or_none(id=scan.id)
                if db_scan and db_scan.status == "cancelled":
                    raise Exception("Scan was cancelled by the user")
                
                # Prevent overwriting a status change that happened during node execution
                scan.status = db_scan.status if db_scan else scan.status

                saved_count = state.get("_saved_log_count", 0)
                current_logs = state.get("node_logs", [])
                
                for i in range(saved_count, len(current_logs)):
                    log_entry = current_logs[i]
                    await ScanLog.create(
                        scan_result=scan,
                        step=log_entry.get("step", "Unknown"),
                        tokens_input=log_entry.get("tokens_input", 0),
                        tokens_output=log_entry.get("tokens_output", 0),
                        model_name=log_entry.get("model_name"),
                        message=log_entry.get("message", "")
                    )
                state["_saved_log_count"] = len(current_logs)
                
                report_obj = {
                    "scanner": {
                        "vulnerabilities": state.get("scan_results", {}).get("vulnerabilities", []),
                        "detected_libraries": state.get("scan_results", {}).get("detected_libraries", {}),
                    },
                    "ecosystem": state.get("ecosystem", {}),
                    "analysis": state.get("analysis_results", []),
                    "remediation": [
                        {
                            "path": fix.get("path", ""),
                            "original_code": fix.get("original_code", "")[:3000],
                            "fix_code": fix.get("fix_code", "")[:3000],
                            "test_code": fix.get("test_code", "")[:2000],
                            "type": fix.get("type", ""),
                        }
                        for fix in state.get("remediation_plan", [])
                    ],
                    "verification": [
                        {
                            "path": fix.get("path", ""),
                            "verified": fix.get("verified", False),
                            "error": fix.get("error", "")[:500] if fix.get("error") else None,
                        }
                        for fix in state.get("verified_fixes", [])
                    ],
                    "report": state.get("final_report", {}),
                }
                
                scan.report_data = report_obj
                scan.trivy_scan = state.get("scan_results", {})
                scan.semgrep_scan = state.get("analysis_results", [])
                await scan.save()

            flow = GuardianFlow()
            shared_state = {
                "repo_url": repo_url,
                "scan_id": scan.id,
                "repo_path": repo_path or ".",
                "pr_number": pr_number,
                "commit_sha": commit_sha,
                "repo_full_name": repo_full_name,
                "target_url": target_url,
                "github_token": github_token,
                "token_usage": {"input": 0, "output": 0},
                "node_logs": [],  # Per-node execution logs
                "on_node_complete": on_node_complete,
            }
            
            # Run the flow
            await flow.run_async(shared_state)
            
            # DEBUG: Log what the flow produced
            print(f"\n{'='*50}")
            print(f"DEBUG: Flow completed. shared_state keys: {list(shared_state.keys())}")
            print(f"DEBUG: token_usage = {shared_state.get('token_usage')}")
            print(f"DEBUG: node_logs count = {len(shared_state.get('node_logs', []))}")
            for i, log in enumerate(shared_state.get('node_logs', [])):
                print(f"DEBUG: node_logs[{i}] = {log}")
            print(f"{'='*50}\n")
            
            # Ensure the final state is saved (in case any logs were added after the last completed node)
            await on_node_complete(shared_state)
            
            # Update ScanResult - FINISHED
            scan.status = "finished" 
            scan.ended_at = datetime.now(timezone.utc)
            await scan.save()
            print(f"Scan {scan.id} finished successfully.")
            
            # Determine finding counts for commit status
            vuln_count = len(shared_state.get("scan_results", {}).get("vulnerabilities", []))
            
            if repo_full_name and commit_sha != "HEAD" and github_token:
                if vuln_count > 0:
                    set_commit_status(repo_full_name, commit_sha, "failure",
                                      f"Found {vuln_count} vulnerabilities", github_token)
                else:
                    set_commit_status(repo_full_name, commit_sha, "success",
                                      "No vulnerabilities found", github_token)
            
            return {"scan_id": scan.id, "status": "finished"}
            
        except Exception as e:
            import traceback
            print(f"Scan failed: {e}")
            traceback.print_exc()
            
            # Crash-safe: try to save partial state before marking as failed
            if scan:
                try:
                    # Attempt to flush any pending logs/report data
                    if 'shared_state' in locals():
                        db_scan = await ScanResult.get_or_none(id=scan.id)
                        if db_scan and db_scan.status == "cancelled":
                            # Avoid flushing and definitely avoid setting to failed
                            pass
                        else:
                            await on_node_complete(shared_state)
                            scan.status = "failed"
                            scan.ended_at = datetime.now(timezone.utc)
                            await scan.save()
                except Exception as save_err:
                    print(f"Failed to update scan status: {save_err}")
            
            if repo_full_name and commit_sha != "HEAD" and github_token:
                set_commit_status(repo_full_name, commit_sha, "error",
                                  f"Scan failed: {str(e)[:100]}", github_token)
            
            return {"status": "failed", "error": str(e)}
        finally:
            await close_db()
            # Clean up cloned repo
            if repo_path and os.path.exists(repo_path):
                print(f"Cleaning up cloned repo: {repo_path}")
                shutil.rmtree(repo_path, ignore_errors=True)

    return asyncio.run(run_flow())
