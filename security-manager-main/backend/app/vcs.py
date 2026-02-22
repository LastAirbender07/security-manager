from abc import ABC, abstractmethod
import requests

class VCProvider(ABC):
    @abstractmethod
    def fetch_file(self, repo_url: str, file_path: str, ref: str) -> str:
        pass

    @abstractmethod
    def post_comment(self, repo_url: str, pr_number: int, file_path: str, line: int, body: str):
        pass

    @abstractmethod
    def get_pr_diff(self, repo_url: str, pr_number: int) -> str:
        """Returns the raw diff of the PR"""
        pass

class GitHubProvider(VCProvider):
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def fetch_file(self, repo_url: str, file_path: str, ref: str) -> str:
        # Simplified: Assumes repo_url is "owner/repo"
        api_url = f"https://api.github.com/repos/{repo_url}/contents/{file_path}?ref={ref}"
        resp = requests.get(api_url, headers=self.headers)
        if resp.status_code == 200:
            import base64
            content = resp.json().get("content", "")
            return base64.b64decode(content).decode("utf-8")
        raise Exception(f"Failed to fetch file: {resp.text}")

    def post_comment(self, repo_url: str, pr_number: int, file_path: str, line: int, body: str):
        # GitHub PR Review Comment API
        api_url = f"https://api.github.com/repos/{repo_url}/pulls/{pr_number}/comments"
        payload = {
            "body": body,
            "path": file_path,
            "line": line, # Depending on API version, might need position or side
            "side": "RIGHT"
        }
        resp = requests.post(api_url, json=payload, headers=self.headers)
        if resp.status_code not in [200, 201]:
            print(f"Failed to post comment: {resp.text}")

    def get_pr_diff(self, repo_url: str, pr_number: int) -> str:
        api_url = f"https://api.github.com/repos/{repo_url}/pulls/{pr_number}"
        # Fetch Diff media type
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        resp = requests.get(api_url, headers=headers)
        return resp.text
