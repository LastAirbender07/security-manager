from pocketflow import AsyncNode
import os
import json
import time
import google.generativeai as genai


TOON_PROMPT = """You are a DevOps expert. Based on the scan results below, determine the correct sandbox environment configuration for verifying code fixes.

## Dependency Scan Results (from Trivy)
{trivy_summary}

## Detected Libraries (from source code imports)
{libraries_summary}

## Requirements
Return ONLY a valid JSON object where the KEYS are file extensions (e.g., ".py", ".js", ".tsx", ".env") and the VALUES are the sandbox configurations for that specific extension.
For each extension, provide these exact keys:
- "language": programming language (e.g., "python", "javascript", "typescript", "text")
- "docker_image": smallest official Docker image for this runtime (e.g., "python:3.11-alpine", "node:20-alpine", "alpine:latest")
- "dep_install_cmd": shell command to install dependencies inside /check directory. Use quiet flags. Example: "cd /check && pip install -r requirements.txt -q" (or empty string if not needed)
- "syntax_cmd": array of command parts to check syntax. Example: ["python", "-m", "py_compile"]
- "test_cmd": array of command parts to run the file. Example: ["python"]

Example JSON format:
{{
  ".py": {{"language": "python", "docker_image": "python:3.11-alpine", "dep_install_cmd": "pip install -r requirements.txt -q", "syntax_cmd": ["python", "-m", "py_compile"], "test_cmd": ["python"]}},
  ".tsx": {{"language": "typescript", "docker_image": "node:20-alpine", "dep_install_cmd": "npm install --no-audit --no-fund --ignore-scripts --silent", "syntax_cmd": ["npx", "tsc", "--noEmit"], "test_cmd": ["npx", "jest"]}},
  ".env": {{"language": "text", "docker_image": "alpine:latest", "dep_install_cmd": "", "syntax_cmd": [], "test_cmd": []}}
}}

## Rules
- Include configurations for all extensions present in the project based on the detected libraries.
- For configuration files (YAML, JSON, ENV), provide a minimal generic alpine configuration with empty test commands.
- The dep_install_cmd must work inside a Docker container with /check as the project root
- Redirect stderr to /dev/null in dep_install_cmd to keep output clean
- Return ONLY the JSON, no markdown, no explanation

## JSON Response:"""

MAX_RETRIES = 3


class EcosystemDetectionNode(AsyncNode):
    """
    Uses Trivy dependency scan + detected libraries from imports + Gemini AI
    to dynamically determine the verification sandbox environment.
    """

    async def prep_async(self, shared):
        scan_results = shared.get("scan_results", {})
        trivy_raw = scan_results.get("trivy_raw", {})
        detected_libraries = scan_results.get("detected_libraries", {})
        return trivy_raw, detected_libraries

    async def exec_async(self, prep_res):
        trivy_raw, detected_libraries = prep_res
        print("Ecosystem: Analyzing with AI...")

        trivy_summary = self._extract_dependency_summary(trivy_raw)
        libraries_summary = self._format_libraries(detected_libraries)

        # If no info, fallback gracefully instead of failing the whole pipeline
        if not trivy_summary.strip() and not libraries_summary.strip():
            print("Ecosystem: No dependency data found. Falling back to generic alpine.")
            return {
                ".txt": {
                    "language": "generic",
                    "docker_image": "alpine:latest",
                    "dep_install_cmd": "echo 'No dependencies to install'",
                    "syntax_cmd": ["echo", "'No syntax check'"],
                    "test_cmd": ["echo", "'No tests'"]
                },
                "_tokens": {"input": 0, "output": 0}
            }

        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise RuntimeError("Ecosystem: No GEMINI_API_KEY set. Cannot proceed.")
        else:
            print(f"Ecosystem: GEMINI_API_KEY resolved as {gemini_key}")

        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = TOON_PROMPT.format(
            trivy_summary=trivy_summary or "No Trivy dependency data available.",
            libraries_summary=libraries_summary or "No libraries detected from source."
        )
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"Ecosystem: Gemini call attempt {attempt}/{MAX_RETRIES}...")
                response = model.generate_content(prompt)
                
                # Debug: inspect full response
                print(f"Ecosystem DEBUG: prompt_feedback = {getattr(response, 'prompt_feedback', 'N/A')}")
                print(f"Ecosystem DEBUG: candidates count = {len(response.candidates) if response.candidates else 0}")
                if response.candidates:
                    c = response.candidates[0]
                    print(f"Ecosystem DEBUG: finish_reason = {c.finish_reason}")
                    print(f"Ecosystem DEBUG: safety_ratings = {c.safety_ratings}")
                
                raw_text = response.text.strip()
                print(f"Ecosystem DEBUG: raw_text = {raw_text[:300]}")
                input_tokens = 0
                output_tokens = 0
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    meta = response.usage_metadata
                    print(f"Ecosystem DEBUG: usage_metadata = {meta}")
                    input_tokens = getattr(meta, 'prompt_token_count', 0) or getattr(meta, 'input_tokens', 0) or 0
                    output_tokens = getattr(meta, 'candidates_token_count', 0) or getattr(meta, 'output_tokens', 0) or 0

                config = self._parse_ai_response(raw_text)
                config["_tokens"] = {"input": input_tokens, "output": output_tokens}

                print(f"Ecosystem: AI determined config for {len(config) - 1} extensions.")
                return config

            except RuntimeError:
                raise
            except Exception as e:
                import traceback
                last_error = e
                print(f"Ecosystem: Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                traceback.print_exc()
                if attempt < MAX_RETRIES:
                    wait = attempt * 2
                    print(f"Ecosystem: Retrying in {wait}s...")
                    time.sleep(wait)

        raise RuntimeError(f"Ecosystem: Gemini failed after {MAX_RETRIES} attempts. Last error: {last_error}")

    def _extract_dependency_summary(self, trivy_raw):
        """Extract dependency file targets and packages from Trivy JSON."""
        if not trivy_raw or "Results" not in trivy_raw:
            return ""

        lines = []
        for result in trivy_raw.get("Results", []):
            target = result.get("Target", "unknown")
            result_type = result.get("Type", "unknown")
            packages = result.get("Packages", [])

            pkg_names = [p.get("Name", "") for p in packages[:20]]
            pkg_summary = ", ".join(pkg_names) if pkg_names else "no packages listed"

            lines.append(f"- File: {target} | Type: {result_type} | Packages: {pkg_summary}")

        return "\n".join(lines)

    def _format_libraries(self, detected_libraries):
        """Format detected libraries into a readable summary."""
        if not detected_libraries:
            return ""

        lines = []
        for lang, libs in detected_libraries.items():
            lines.append(f"- {lang}: {', '.join(libs)}")
        return "\n".join(lines)

    def _parse_ai_response(self, raw_text):
        """Parse and validate the AI's JSON response."""
        text = raw_text.strip()
        import re
        # Extract json content if enclosed in markdown backticks
        json_match = re.search(r'```(?:json)?(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if json_match:
            text = json_match.group(1).strip()
        else:
            # Fallback cleanup just in case
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            config = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Ecosystem: Failed to parse AI response as JSON: {text[:200]}")

        # Ensure all nested configs have the required lists
        required = ["language", "docker_image", "dep_install_cmd", "syntax_cmd", "test_cmd"]
        for ext, ext_cfg in config.items():
            if not isinstance(ext_cfg, dict):
                continue
            for key in required:
                if key not in ext_cfg:
                    raise RuntimeError(f"Ecosystem: AI response for {ext} missing required key '{key}'")

            if isinstance(ext_cfg["syntax_cmd"], str):
                ext_cfg["syntax_cmd"] = ext_cfg["syntax_cmd"].split()
            if isinstance(ext_cfg["test_cmd"], str):
                ext_cfg["test_cmd"] = ext_cfg["test_cmd"].split()

        return config

    async def post_async(self, shared, prep_res, exec_res):
        _, detected_libraries = prep_res
        exec_res["_detected_libraries"] = detected_libraries
        shared["ecosystem"] = exec_res

        tokens = exec_res.pop("_tokens", {"input": 0, "output": 0})

        lang_count = len([k for k in exec_res.keys() if k.startswith('.')])
        shared.setdefault("node_logs", []).append({
            "step": "Ecosystem Detection",
            "tokens_input": tokens["input"],
            "tokens_output": tokens["output"],
            "model_name": "gemini-2.5-flash",
            "message": f"AI-detected {lang_count} languages/configs"
        })

        print(f"Ecosystem: Discovered configurations for {lang_count} extensions.")
        return "default"
