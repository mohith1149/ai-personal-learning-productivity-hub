"""GitHub helpers. Login required. Read-only: nothing here writes to GitHub or saves a project."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.core.deps import CurrentUser
from app.routers.challenges import _GH_STATUS, get_github
from app.schemas import github as s
from app.services import github as gh
from app.services import github_import

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/status")
def github_status(user: CurrentUser):
    return {"token_configured": bool(get_settings().github_token)}


@router.post("/repo-preview", response_model=s.RepoPreviewOut)
def repo_preview(body: s.RepoPreviewIn, user: CurrentUser, client: Annotated[gh.GitHubClient, Depends(get_github)]):
    """Read a repository and suggest project details (name, description, tech stack, start date) to prefill the form."""
    try:
        return github_import.preview(client.get_repo(body.repo_url))
    except gh.GitHubError as e:
        raise HTTPException(_GH_STATUS.get(e.code, 502), e.message) from None
