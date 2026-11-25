"""Turn a GitHub repository's public facts into suggested project-form fields (no LLM; the AI version is Phase 6)."""
import re

from app.services.github import RepoInfo

MAX_DESCRIPTION = 400
_BADGE_OR_HTML = re.compile(r"^(\s*(!\[|\[!\[|<|\||---|===|```|#))")


def _first_paragraph(readme: str | None) -> str | None:
    """First prose paragraph of the README: skips headings, badges, HTML, tables and code fences."""
    if not readme:
        return None
    para: list[str] = []
    in_code = False
    for line in readme.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line.strip():
            if para:
                break
            continue
        if _BADGE_OR_HTML.match(line) and not para:
            continue
        if line.lstrip().startswith(">") and not para:
            line = line.lstrip("> ").strip()
        para.append(line.strip())
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", " ".join(para))  # keep link text, drop the URL
    text = re.sub(r"[*_`]", "", text).strip()
    return text[:MAX_DESCRIPTION] or None


def preview(info: RepoInfo) -> dict:
    stack: list[str] = []
    for item in [*info.languages[:5], *info.topics[:5]]:
        if item.lower() not in {s.lower() for s in stack}:
            stack.append(item)
    return {
        "title": info.name, "description": (info.description or "").strip() or _first_paragraph(info.readme),
        "tech_stack": stack, "repo_url": info.url, "start_date": info.created_at.date() if info.created_at else None,
        "readme_found": info.readme is not None,
    }
