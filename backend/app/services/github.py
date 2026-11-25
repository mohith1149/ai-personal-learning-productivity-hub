"""Read-only GitHub client used to verify that a challenge's commit really exists.

What it does: `GET /repos/{owner}/{repo}/commits/{sha}` and report what GitHub says.
What it never does: write to GitHub, read anything but that one commit, or fetch a URL the user typed (only
`owner`/`repo`/`sha` parsed and validated out of it are sent, so there is no SSRF surface).

Security: the optional token (GITHUB_TOKEN, needed only for private repos / higher rate limits) is sent in the
Authorization HEADER and never logged or put in an error message. Error text is written here, never copied from GitHub.
Public repos work with no token (60 requests/hour).
"""
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

API_BASE = "https://api.github.com"
_REPO_URL = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100})$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")


class GitHubError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str | None
    committed_at: datetime | None
    parents: int
    files_changed: int
    additions: int
    deletions: int
    url: str


@dataclass
class RepoInfo:
    owner: str
    name: str
    description: str | None
    topics: list[str]
    languages: list[str]  # most used first
    readme: str | None
    created_at: datetime | None
    url: str


def parse_repo_url(url: str) -> tuple[str, str]:
    m = _REPO_URL.match(url.strip().rstrip("/").removesuffix(".git"))
    if not m:
        raise GitHubError("bad_repo", "The repository must look like https://github.com/owner/repo")
    return m.group(1), m.group(2)


class GitHubClient:
    def __init__(self, token: str | None = None, http: httpx.Client | None = None):
        self._headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ai-learning-hub"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)
        self._http = http or httpx.Client(timeout=httpx.Timeout(15.0))

    def close(self) -> None:
        self._http.close()

    def get_commit(self, repo_url: str, sha: str) -> CommitInfo:
        owner, repo = parse_repo_url(repo_url)
        if not _SHA.match(sha):
            raise GitHubError("bad_sha", "That is not a commit hash (7 to 40 hex characters)")
        r = self._request(f"/repos/{owner}/{repo}/commits/{sha}")
        if r.status_code == 200:
            return self._parse(r.json())
        raise self._error(r, f"commit {sha[:12]}", owner, repo)

    def _request(self, path: str, headers: dict | None = None) -> httpx.Response:
        try:
            return self._http.get(f"{API_BASE}{path}", headers={**self._headers, **(headers or {})})
        except httpx.HTTPError:
            raise GitHubError("network", "Couldn't reach GitHub. Check your connection and try again") from None

    def get_repo(self, repo_url: str) -> RepoInfo:
        """Public facts about a repository, used to prefill the project form. Languages and README are best effort."""
        owner, repo = parse_repo_url(repo_url)
        r = self._request(f"/repos/{owner}/{repo}")
        if r.status_code != 200:
            raise self._error(r, "repository", owner, repo)
        d = r.json()
        langs = self._request(f"/repos/{owner}/{repo}/languages")
        languages = [k for k, _ in sorted((langs.json() if langs.status_code == 200 else {}).items(), key=lambda kv: -kv[1])]
        rd = self._request(f"/repos/{owner}/{repo}/readme", {"Accept": "application/vnd.github.raw+json"})
        raw = d.get("created_at")
        return RepoInfo(owner=owner, name=d.get("name") or repo, description=d.get("description"), topics=list(d.get("topics") or []),
                        languages=languages, readme=rd.text[:20000] if rd.status_code == 200 else None,
                        created_at=datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None, url=f"https://github.com/{owner}/{repo}")

    def _error(self, r: httpx.Response, what: str, owner: str, repo: str) -> GitHubError:
        if r.status_code in (403, 429) and (r.headers.get("x-ratelimit-remaining") == "0" or r.status_code == 429):
            hint = "" if self.has_token else " Setting GITHUB_TOKEN raises the limit"
            return GitHubError("rate_limited", f"GitHub's request limit was reached. Try again later.{hint}")
        if r.status_code in (404, 422):
            hint = "" if self.has_token else " (a private repository needs GITHUB_TOKEN)"
            return GitHubError("not_found", f"GitHub has no {what} in {owner}/{repo}{hint}")
        if r.status_code in (401, 403):
            return GitHubError("bad_token", "GitHub rejected the configured GITHUB_TOKEN")
        return GitHubError("api_error", f"GitHub answered with an unexpected status ({r.status_code})")

    @staticmethod
    def _parse(d: dict) -> CommitInfo:
        commit = d.get("commit") or {}
        who = commit.get("committer") or commit.get("author") or {}
        raw = who.get("date")
        when = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        stats = d.get("stats") or {}
        return CommitInfo(
            sha=d.get("sha", ""), message=commit.get("message", ""), author=(commit.get("author") or {}).get("name"),
            committed_at=when, parents=len(d.get("parents") or []), files_changed=len(d.get("files") or []),
            additions=int(stats.get("additions") or 0), deletions=int(stats.get("deletions") or 0), url=d.get("html_url", ""),
        )
