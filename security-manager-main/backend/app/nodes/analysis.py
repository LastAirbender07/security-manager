from pocketflow import AsyncNode
import subprocess
import os
import json

class AnalysisNode(AsyncNode):
    async def prep_async(self, shared):
        return shared.get("scan_results", {"vulnerabilities": []}), shared.get("target_url", "")

    async def exec_async(self, prep_res):
        scan_results, target_url = prep_res
        findings = scan_results.get("vulnerabilities", [])
        
        print(f"Analysis: Analyzing {len(findings)} findings from Scanner...")
        
        import os
        import subprocess
        
        target_url = target_url # From prep_res
        zap_scan_type = os.getenv("ZAP_SCAN_TYPE", "baseline") # baseline or full
        zap_volume_name = os.getenv("ZAP_VOLUME_NAME")
        host_work_dir = os.getenv("HOST_WORK_DIR")

        print(f"DEBUG: ZAP_VOLUME_NAME='{zap_volume_name}'")
        print(f"DEBUG: HOST_WORK_DIR='{host_work_dir}'")
        print(f"DEBUG: All Env Vars: {json.dumps(dict(os.environ), default=str)}")
        
        if target_url:
            print(f"Analysis: Running ZAP {zap_scan_type.title()} Scan on {target_url}...")
            
            # Select script based on type
            script = "zap-baseline.py" if zap_scan_type == "baseline" else "zap-full-scan.py"
            
            # Docker Command
            # Priority 1: Host Mount (Best for DooD where we want report back in our mapped volume)
            if host_work_dir:
                 volume_mount = f"{host_work_dir}:/zap/wrk/:rw"
                 report_read_path = "zap_report.json"
                 print(f"Analysis: Using HOST_WORK_DIR mount '{host_work_dir}'")
            
            # Priority 2: Named Volume (If configured)
            elif zap_volume_name:
                # Named volume mount: volume_name:/zap/wrk/:rw
                # We need to read the report from the volume too... or from the path mapped to the volume.
                # In docker-compose, we mapped zap-data:/zap-data in the worker.
                # So we should tell ZAP to write to /zap/wrk/, and we map the named volume there.
                # BUT, we need to access that file from THIS container (the worker).
                # The worker has the volume mounted at /zap-data (as per our docker-compose update).
                # So ZAP should write to /zap/wrk inside its container, which is mapped to the named volume.
                # We interpret /zap/wrk in ZAP container == /zap-data in Worker container.
                
                volume_mount = f"{zap_volume_name}:/zap/wrk/:rw"
                report_read_path = "/zap-data/zap_report.json"
                print(f"Analysis: Using named volume '{zap_volume_name}' mapped to '{report_read_path}'")
            else:
                # Fallback to current directory bind mount (Will fail in DooD if path doesn't match host)
                volume_mount = f"{os.getcwd()}:/zap/wrk/:rw"
                report_read_path = "zap_report.json"
                print(f"Analysis: Using bind mount '{os.getcwd()}'")

            cmd = [
                "docker", "run", "--rm",
                "-v", volume_mount,
                "-t", "ghcr.io/zaproxy/zaproxy:stable",
                script,
                "-t", target_url,
                "-J", "zap_report.json"
            ]
            
            try:
                # ZAP returns exit codes: 0=Clean, 1=Issues, 2=Failure
                print(f"Analysis: Executing ZAP: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                # Check for finding report
                if os.path.exists(report_read_path):
                     try:
                         with open(report_read_path, "r") as f:
                             zap_data = json.load(f)
                             
                         site = zap_data.get("site", [{}])[0]
                         alerts = site.get("alerts", [])
                         
                         print(f"DAST: ZAP found {len(alerts)} alerts.")
                         
                         for alert in alerts:
                             findings.append({
                                 "id": f"zap-{alert.get('pluginid')}",
                                 "path": target_url, # It's application level
                                 "line": 0,
                                 "msg": f"DAST: {alert.get('name')} (Risk: {alert.get('riskdesc')})",
                                 "severity": alert.get("riskcode", "0"), # 3=High, 2=Med, 1=Low
                                 "type": "DAST",
                                 "desc": alert.get("desc")
                             })
                         
                         os.remove(report_read_path) # Cleanup
                     except Exception as e:
                         print(f"DAST: Failed to parse ZAP report: {e}")
                else:
                    print(f"DAST: No ZAP report generated at {report_read_path}")
                    if result.stderr:
                        print(f"DAST Output: {result.stderr}")
                    
            except Exception as e:
                print(f"DAST: ZAP execution failed: {e}")
        else:
             print("DAST: No valid target URL provided. Skipping dynamic scan.")

        return findings

    async def post_async(self, shared, prep_res, exec_res):
        shared["analysis_results"] = exec_res
        finding_count = len(exec_res) if exec_res else 0
        shared.setdefault("node_logs", []).append({
            "step": "Analysis",
            "tokens_input": 0,
            "tokens_output": 0,
            "model_name": None,
            "message": f"DAST analysis: {finding_count} findings"
        })
        return "default"
