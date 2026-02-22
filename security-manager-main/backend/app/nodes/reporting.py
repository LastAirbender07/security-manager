from pocketflow import AsyncNode
from app.models import ScanResult
import logging

class ReportingNode(AsyncNode):
    async def prep_async(self, shared):
        return {
            "scan_id": shared.get("scan_id"),
            "verified_fixes": shared.get("verified_fixes"),
            "pr_number": shared.get("pr_number", 0),
            "commit_sha": shared.get("commit_sha", "HEAD"),
            "repo_full_name": shared.get("repo_full_name", ""),
            "scan_results": shared.get("scan_results", {}),
        }

    async def exec_async(self, prep_res):
        scan_id = prep_res["scan_id"]
        verified_fixes = prep_res["verified_fixes"]
        pr_number = prep_res["pr_number"]
        commit_sha = prep_res["commit_sha"]
        repo_full_name = prep_res["repo_full_name"]
        vuln_count = len(prep_res.get("scan_results", {}).get("vulnerabilities", []))
        
        logging.info(f"Reporting: Finalizing scan {scan_id}")
        
        report = {
            "scan_id": scan_id,
            "status": "completed",
            "verified_fixes": len(verified_fixes) if verified_fixes else 0,
            "total_vulnerabilities": vuln_count,
            "details": verified_fixes,
        }
        
        if pr_number:
            report["pr_number"] = pr_number
            report["commit_sha"] = commit_sha
            report["repo"] = repo_full_name
        
        print(f"Reporting: Scan {scan_id} completed — {vuln_count} vulns, {report['verified_fixes']} verified fixes.")
        if pr_number:
            print(f"Reporting: PR #{pr_number} on {repo_full_name} (sha: {commit_sha[:7]})")
        
        return report

    async def post_async(self, shared, prep_res, exec_res):
        shared["final_report"] = exec_res
        shared.setdefault("node_logs", []).append({
            "step": "Reporting",
            "tokens_input": 0,
            "tokens_output": 0,
            "model_name": None,
            "message": f"Report generated: {exec_res.get('verified_fixes', 0)} verified fixes"
        })
        return "default"

