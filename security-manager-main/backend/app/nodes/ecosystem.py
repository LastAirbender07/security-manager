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
Return ONLY a valid JSON object with these exact keys:
- "language": primary programming language (e.g., "python", "javascript", "java", "go", "ruby")
- "docker_image": smallest official Docker image for this language runtime (e.g., "python:3.11-alpine", "node:20-alpine")
- "dep_install_cmd": shell command to install all dependencies inside /check directory. Use quiet/silent flags. Example: "cd /check && pip install -r requirements.txt -q"
- "syntax_cmd": array of command parts to check syntax of a single file. Example: ["python", "-m", "py_compile"]
- "test_cmd": array of command parts to run a single file. Example: ["python"]

## Rules
- Pick the SMALLEST Alpine-based image when possible
- The dep_install_cmd must work inside a Docker container with /check as the project root
- Redirect stderr to /dev/null in dep_install_cmd to keep output clean
- If multiple languages are detected, pick the PRIMARY one (most dependency files)
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
                "language": "generic",
                "docker_image": "alpine:latest",
                "dep_install_cmd": "echo 'No dependencies to install'",
                "syntax_cmd": ["echo", "'No syntax check'"],
                "test_cmd": ["echo", "'No tests'"],
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

                print(f"Ecosystem: AI determined -> {config['language']}, image={config['docker_image']}")
                return config

            except RuntimeError:
                raise
            except Exception as e:
                last_error = e
                print(f"Ecosystem: Attempt {attempt}/{MAX_RETRIES} failed: {e}")
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
        text = raw_text
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            config = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Ecosystem: Failed to parse AI response as JSON: {text[:200]}")

        required = ["language", "docker_image", "dep_install_cmd", "syntax_cmd", "test_cmd"]
        for key in required:
            if key not in config:
                raise RuntimeError(f"Ecosystem: AI response missing required key '{key}'")

        if isinstance(config["syntax_cmd"], str):
            config["syntax_cmd"] = config["syntax_cmd"].split()
        if isinstance(config["test_cmd"], str):
            config["test_cmd"] = config["test_cmd"].split()

        return config

    async def post_async(self, shared, prep_res, exec_res):
        _, detected_libraries = prep_res
        exec_res["_detected_libraries"] = detected_libraries
        shared["ecosystem"] = exec_res

        tokens = exec_res.pop("_tokens", {"input": 0, "output": 0})

        lang = exec_res.get("language", "unknown")
        image = exec_res.get("docker_image", "unknown")
        shared.setdefault("node_logs", []).append({
            "step": "Ecosystem Detection",
            "tokens_input": tokens["input"],
            "tokens_output": tokens["output"],
            "model_name": "gemini-2.5-flash",
            "message": f"AI-detected: {lang}, image={image}"
        })

        print(f"Ecosystem: Set -> language={lang}, image={image}")
        return "default"
