from pocketflow import AsyncNode

class RemediationNode(AsyncNode):
    async def prep_async(self, shared):
        return shared.get("analysis_results", []), shared

    async def prep_async(self, shared):
        return shared.get("analysis_results", []), shared

    async def exec_async(self, prep_res):
        findings, shared = prep_res
        import os
        import google.generativeai as genai
        from collections import defaultdict
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("Remediation Error: GEMINI_API_KEY not found")
            return []
        else:
            print(f"Remediation: GEMINI_API_KEY resolved as {gemini_key}")
        max_retries = int(os.getenv("MAX_RETRIES", "3"))
        repo_path = shared.get("repo_path", ".")
        
        # Token usage tracking
        total_input_tokens = shared.get("token_usage", {}).get("input", 0)
        total_output_tokens = shared.get("token_usage", {}).get("output", 0)
        
        # Retry Logic
        current_retry = shared.get("retry_count", 0)
        previous_fixes = shared.get("verified_fixes", []) 
        
        if previous_fixes: 
             if current_retry >= max_retries:
                 print(f"Remediation: Max retries ({max_retries}) reached. Giving up.")
                 shared["remediation_plan"] = []
                 return []
             
             print(f"Remediation: Retry {current_retry + 1}/{max_retries}. Attempting to fix again...")
             shared["retry_count"] = current_retry + 1
        else:
             shared["retry_count"] = 0

        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        # Group findings by file
        findings_by_file = defaultdict(list)
        for f in findings:
            findings_by_file[f['path']].append(f)

        max_files = int(os.getenv("MAX_FILES_TO_REMEDIATE", "5"))
        # Get only up to max_files keys to process
        files_to_process = list(findings_by_file.keys())[:max_files]
        if len(findings_by_file) > max_files:
            print(f"Remediation: Capping remediation to {max_files} files out of {len(findings_by_file)} vulnerable files to prevent timeout.")

        fixes = []
        
        for file_path in files_to_process:
            file_findings = findings_by_file[file_path]
            full_path = os.path.join(repo_path, file_path)
            
            try:
                with open(full_path, 'r') as f:
                    content = f.read()
            except FileNotFoundError:
                print(f"Remediation Error: Could not read file {full_path}")
                continue

            print(f"Remediation: Generating fix for {file_path} ({len(file_findings)} issues) using Gemini Pro...")
            
            # Construct Prompt
            import toons

            # Determine if this file needs tests based on extension
            ext = os.path.splitext(file_path)[1].lower()
            code_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php", ".cs", ".cpp", ".c"}
            needs_test = ext in code_extensions

            reqs = [
                "Return the FULLY CORRECTED file content.",
            ]
            
            if needs_test:
                reqs.extend([
                    "PROVIDE A STANDALONE UNIT TEST file to verify the fix works and the vulnerability is gone.",
                    "Use the following format EXACTLY:\n### FIX\n(The full corrected code here)\n### TEST\n(The full unit test code here)",
                    f"Ensure imports are correct. For the test, assume the fixed file is named '{os.path.basename(file_path)}' and is in the same directory.",
                    "CRITICAL FIX RULES:",
                    "- If applicable to the language, ensure side effects form module imports are prevented (e.g., `if __name__ == '__main__':` in Python).",
                    "- Ensure EVERY required function/dependency is defined or imported.",
                    "CRITICAL TEST RULES:",
                    "- Write BEHAVIORAL tests, NOT implementation-specific tests. Test WHAT the code does, not HOW it does it internally.",
                    "- NEVER assert on specific hash prefixes, output formats, or library-specific string patterns (e.g. do NOT check startswith('pbkdf2:') or startswith('$2b$')).",
                    "- Instead, test that: (1) the output is not plaintext, (2) the same input produces consistent output, (3) functions don't raise exceptions, (4) security-sensitive operations use the correct API.",
                    "- The test file must ONLY use the standard testing framework for this language + modules that the fix code itself imports. Do NOT introduce new third-party testing dependencies.",
                    "- Every test must actually import and call functions from the fixed file."
                ])
            else:
                reqs.extend([
                    "Since this is a configuration, data, or text file, DO NOT generate a unit test.",
                    "Use the following format EXACTLY:\n### FIX\n(The full corrected code here)\n### TEST\nNone",
                    "CRITICAL FIX RULES:",
                    "- Keep the original formatting and spacing exactly as it was.",
                    "- Ensure valid syntax for the target file type."
                ])

            # Construct Prompt Data for TOON
            prompt_data = {
                "role": "senior security engineer",
                "task": "Fix security vulnerabilities" + (" and provide a verification test" if needs_test else ""),
                "issues": [{"line": f.get('line'), "msg": f.get('msg')} for f in file_findings],
                "file_content": content,
                "requirements": reqs
            }

            if previous_fixes:
                 # Find previous error for this file
                 last_error = next((f.get("error") for f in previous_fixes if f.get("path") == file_path), "Unknown error")
                 prompt_data["previous_attempt_error"] = last_error
                 prompt_data["instruction"] = "Fix the code to resolve the previous error."

            prompt = toons.dumps(prompt_data)

            try:
                response = model.generate_content(prompt)
                raw_text = response.text.strip()
                
                # Track token usage from Gemini response
                input_tokens = 0
                output_tokens = 0
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    meta = response.usage_metadata
                    print(f"Remediation DEBUG: usage_metadata = {meta}")
                    # Try multiple attribute names (varies by SDK version)
                    input_tokens = getattr(meta, 'prompt_token_count', 0) or getattr(meta, 'input_tokens', 0) or 0
                    output_tokens = getattr(meta, 'candidates_token_count', 0) or getattr(meta, 'output_tokens', 0) or 0
                else:
                    print(f"Remediation DEBUG: No usage_metadata found. response type={type(response)}, dir={[a for a in dir(response) if 'token' in a.lower() or 'usage' in a.lower()]}")
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                print(f"Remediation: Tokens used — input: {input_tokens}, output: {output_tokens}")
                
                fix_code = ""
                test_code = ""
                
                # Parse Response
                if "### FIX" in raw_text:
                    parts = raw_text.split("### TEST")
                    fix_part = parts[0].split("### FIX")[1].strip()
                    test_part = parts[1].strip() if len(parts) > 1 else ""
                    
                    # Clean up backticks
                    if fix_part.startswith("```"): fix_part = fix_part.split("\n", 1)[1]
                    if fix_part.endswith("```"): fix_part = fix_part.rsplit("\n", 1)[0]
                    if test_part.startswith("```"): test_part = test_part.split("\n", 1)[1]
                    if test_part.endswith("```"): test_part = test_part.rsplit("\n", 1)[0]
                    
                    fix_code = fix_part
                    test_code = test_part
                else:
                    # Fallback if AI messes up format, assume whole response is fix
                    fix_code = raw_text
                    
                fixes.append({
                    "path": file_path,
                    "original_code": content,
                    "fix_code": fix_code,
                    "test_code": test_code,
                    "type": "full_file"
                })
            except Exception as e:
                print(f"Remediation: Failed to generate fix with Gemini: {e}")
        
        # Update token usage in shared state
        shared["token_usage"] = {"input": total_input_tokens, "output": total_output_tokens}
        print(f"Remediation: Total tokens — input: {total_input_tokens}, output: {total_output_tokens}")
                
        return fixes

    async def post_async(self, shared, prep_res, exec_res):
        shared["remediation_plan"] = exec_res
        token_usage = shared.get("token_usage", {})
        fix_count = len(exec_res) if exec_res else 0
        shared.setdefault("node_logs", []).append({
            "step": "Remediation",
            "tokens_input": token_usage.get("input", 0),
            "tokens_output": token_usage.get("output", 0),
            "model_name": "gemini-2.5-flash",
            "message": f"Generated {fix_count} fixes"
        })
        return "default"

