from datetime import date as DateT

from pydantic import BaseModel, ConfigDict, Field


class RepoPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repo_url: str = Field(min_length=1, max_length=500)


class RepoPreviewOut(BaseModel):
    """Suggested project fields read from the repository. Nothing is saved; the form shows them for the user to edit."""
    title: str
    description: str | None
    tech_stack: list[str]
    repo_url: str
    start_date: DateT | None
    readme_found: bool
