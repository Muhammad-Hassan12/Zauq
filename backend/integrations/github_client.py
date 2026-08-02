import httpx
from typing import Dict, Any, Optional

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Zauq-Discord-Bot"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        diff_headers = self._headers()
        diff_headers["Accept"] = "application/vnd.github.v3.diff"

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=diff_headers)
            if res.status_code != 200:
                raise RuntimeError(f"GitHub API Error ({res.status_code}): {res.text}")
            
            # Fetch pull request details
            details_res = await client.get(url, headers=self._headers())
            pr_data = details_res.json() if details_res.status_code == 200 else {}

            return {
                "title": pr_data.get("title", f"PR #{pr_number}"),
                "author": pr_data.get("user", {}).get("login", "unknown"),
                "state": pr_data.get("state", "open"),
                "diff": res.text[:4000]  # Truncate diff to fit prompt limits
            }

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=self._headers())
            if res.status_code != 200:
                raise RuntimeError(f"GitHub API Error ({res.status_code}): {res.text}")

            data = res.json()
            return {
                "title": data.get("title", f"Issue #{issue_number}"),
                "author": data.get("user", {}).get("login", "unknown"),
                "state": data.get("state", "open"),
                "body": data.get("body", "No description provided.")[:3000]
            }

    async def get_repo_readme(self, owner: str, repo: str) -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}/readme"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.raw"

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise RuntimeError(f"Failed to fetch README ({res.status_code}): {res.text}")
            return res.text[:8000]

github_client = GitHubClient()
