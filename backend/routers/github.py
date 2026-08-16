import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.integrations.github_client import github_client
from backend.memory.rag import add_server_lore

logger = logging.getLogger("zauq.github")

router = APIRouter(prefix="/api/github", tags=["GitHub Integration"])

class IngestRepoRequest(BaseModel):
    guild_id: str
    owner: str
    repo: str

@router.get("/pr")
async def get_pr_info(owner: str, repo: str, pr_number: int):
    try:
        data = await github_client.get_pr_diff(owner, repo, pr_number)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch PR #{pr_number} for {owner}/{repo}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch GitHub PR info.")

@router.get("/issue")
async def get_issue_info(owner: str, repo: str, issue_number: int):
    try:
        data = await github_client.get_issue(owner, repo, issue_number)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch issue #{issue_number} for {owner}/{repo}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch GitHub issue info.")

ALLOWED_REPOS = [
    "Muhammad-Hassan12/Zauq",
    "discord/discord-api-docs",
]

@router.post("/ingest")
async def ingest_repo_readme(req: IngestRepoRequest):
    repo_full_name = f"{req.owner}/{req.repo}"
    if repo_full_name not in ALLOWED_REPOS:
        raise HTTPException(status_code=403, detail=f"Repository {repo_full_name} is not whitelisted for ingestion.")

    try:
        readme_text = await github_client.get_repo_readme(req.owner, req.repo)
        res = await add_server_lore(req.guild_id, source_type="repo", content=f"Repo {req.owner}/{req.repo} README:\n{readme_text}")
        return {"status": "success", "repo": f"{req.owner}/{req.repo}", "data": res}
    except Exception as e:
        logger.error(f"Failed to ingest repo {repo_full_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to ingest repository README.")
