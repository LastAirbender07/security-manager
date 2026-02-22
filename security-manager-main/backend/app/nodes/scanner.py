from pocketflow import AsyncNode
import subprocess
import json
import os
import re

class ScannerNode(AsyncNode):
    async def prep_async(self, shared):
        repo_path = shared.get("repo_path", ".")
        return repo_path

    async def exec_async(self, repo_path):
        results = {"vulnerabilities": [], "trivy_raw": {}, "detected_libraries": {}}
        
        # SAST: Run Semgrep with advanced security rules
        try:
            print(f"Scanner: Running Semgrep on {repo_path}...")
            # Use specific rulesets to catch deep flaws, SQLi, CSRF, secrets, etc.
            cmd = [
                "semgrep", "scan",
                "--config=p/default",
                "--config=p/security-audit",
                "--config=p/secrets",
                "--json", "--quiet", repo_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                semgrep_out = json.loads(result.stdout)
                raw_findings = semgrep_out.get("results", [])
                for item in raw_findings:
                    results["vulnerabilities"].append({
                        "id": f"semgrep-{item.get('check_id')}",
                        "path": item.get("path"),
                        "line": item.get("start", {}).get("line"),
                        "msg": item.get("extra", {}).get("message"),
                        "severity": item.get("extra", {}).get("severity"),
                        "type": "SAST"
                    })
                print(f"Scanner: Semgrep found {len(raw_findings)} issues.")
            else:
                print(f"Scanner: Semgrep failed: {result.stderr}")
        except FileNotFoundError:
            print("Scanner Error: 'semgrep' not found.")
        except Exception as e:
            print(f"Scanner Error (Semgrep): {e}")

        # SCA: Run Trivy with extensive scanners
        try:
            print(f"Scanner: Running Trivy SCA on {repo_path}...")
            cmd = [
                "trivy", "fs",
                "--scanners", "vuln,secret,misconfig",
                "--format", "json",
                "--quiet", "--list-all-pkgs", repo_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                try:
                    trivy_out = json.loads(result.stdout)
                    if "Results" in trivy_out:
                        count = 0
                        for target in trivy_out["Results"]:
                            for vuln in target.get("Vulnerabilities", []):
                                count += 1
                                results["vulnerabilities"].append({
                                    "id": vuln.get("VulnerabilityID"),
                                    "path": target.get("Target"),
                                    "line": 0,
                                    "msg": f"{vuln.get('PkgName')} {vuln.get('InstalledVersion')} is vulnerable: {vuln.get('Title')}",
                                    "severity": vuln.get("Severity"),
                                    "type": "SCA",
                                    "fix_version": vuln.get("FixedVersion")
                                })
                        print(f"Scanner: Trivy found {count} vulnerabilities.")
                    results["trivy_raw"] = trivy_out
                except json.JSONDecodeError:
                    print("Scanner Error: Failed to parse Trivy output.")
            else:
                print(f"Scanner: Trivy failed: {result.stderr}")
        except FileNotFoundError:
            print("Scanner Error: 'trivy' not found.")
        except Exception as e:
            print(f"Scanner Error (Trivy): {e}")

        # Detect libraries from source code imports
        detected = self._detect_libraries(repo_path)
        results["detected_libraries"] = detected
        if detected:
            print(f"Scanner: Detected libraries from imports -> {detected}")

        return results

    def _detect_libraries(self, repo_path):
        """Parse source files for import statements to detect libraries used."""
        # Map file extension -> language
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".java": "java", ".go": "go", ".rb": "ruby",
            ".rs": "rust", ".php": "php"
        }
        
        # Standard library modules to ignore (top-level only)
        python_stdlib = {
            "os", "sys", "json", "re", "math", "datetime", "time", "random",
            "collections", "functools", "itertools", "pathlib", "subprocess",
            "threading", "multiprocessing", "logging", "unittest", "io",
            "string", "hashlib", "hmac", "base64", "http", "urllib",
            "typing", "abc", "copy", "shutil", "tempfile", "glob",
            "argparse", "csv", "xml", "html", "email", "socket",
            "asyncio", "contextlib", "dataclasses", "enum", "pprint",
            "textwrap", "struct", "sqlite3", "traceback", "warnings"
        }
        
        libraries_by_lang = {}
        
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in (
                'node_modules', '__pycache__', 'venv', '.git', 'env', '.venv', 'dist', 'build'
            )]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in lang_map:
                    continue
                    
                lang = lang_map[ext]
                if lang not in libraries_by_lang:
                    libraries_by_lang[lang] = set()
                
                filepath = os.path.join(root, fname)
                try:
                    with open(filepath, 'r', errors='ignore') as f:
                        content = f.read(10000)  # Read first 10KB
                    
                    if lang == "python":
                        # Match: import flask / from flask import X
                        for m in re.finditer(r'^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', content, re.MULTILINE):
                            lib = m.group(1)
                            if lib not in python_stdlib:
                                libraries_by_lang[lang].add(lib)
                    
                    elif lang in ("javascript", "typescript"):
                        # Match: require('express') / import X from 'express'
                        for m in re.finditer(r'''(?:require\s*\(\s*['"]([^'"./][^'"]*)['"]\)|from\s+['"]([^'"./][^'"]*)['"]\s*)''', content):
                            lib = m.group(1) or m.group(2)
                            if lib:
                                libraries_by_lang[lang].add(lib.split('/')[0])
                    
                    elif lang == "java":
                        # Match: import com.google.gson.Gson
                        for m in re.finditer(r'^import\s+((?:com|org|io|net)\.[a-zA-Z0-9_.]+)', content, re.MULTILINE):
                            libraries_by_lang[lang].add(m.group(1).split('.')[1])
                    
                    elif lang == "go":
                        # Match: "github.com/gin-gonic/gin"
                        for m in re.finditer(r'"(github\.com/[^"]+)"', content):
                            libraries_by_lang[lang].add(m.group(1).split('/')[-1])
                    
                    elif lang == "ruby":
                        # Match: require 'sinatra'
                        for m in re.finditer(r"require\s+['\"]([^'\"]+)['\"]", content):
                            libraries_by_lang[lang].add(m.group(1))

                except Exception:
                    continue
        
        # Convert sets to sorted lists
        return {lang: sorted(libs) for lang, libs in libraries_by_lang.items() if libs}

    async def post_async(self, shared, prep_res, exec_res):
        shared["scan_results"] = exec_res
        vuln_count = len(exec_res.get("vulnerabilities", []))
        shared.setdefault("node_logs", []).append({
            "step": "Scanner",
            "tokens_input": 0,
            "tokens_output": 0,
            "model_name": None,
            "message": f"Semgrep + Trivy: {vuln_count} vulnerabilities found"
        })
        return "default"
