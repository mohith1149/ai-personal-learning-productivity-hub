"""GitHub commit verification: the client against a fake GitHub (httpx.MockTransport) and the /verify endpoint."""
from datetime import datetime, timezone

import httpx
import pytest

from app.main import app
from app.routers.challenges import get_github
from app.services import github as gh
from tests.test_challenges_api import EVIDENCE, REPO, SETUP, TODAY, plan, project  # noqa: F401

FULL = "a1b2c3d4e5f6" + "0" * 28


def commit_json(**kw):
    d = {"sha": FULL, "html_url": f"{REPO}/commit/{FULL}", "parents": [{"sha": "p"}],
         "commit": {"message": "Add retrieval step to RAG pipeline\n\nbody", "author": {"name": "Me"},
                    "committer": {"date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}},
         "stats": {"additions": 40, "deletions": 2}, "files": [{"filename": "a.py"}]}
    d.update(kw)
    return d


def make_client(status=200, body=None, headers=None, token=None, seen=None):
    def handler(req: httpx.Request):
        if seen is not None:
            seen.append(req)
        return httpx.Response(status, json=body if body is not None else commit_json(), headers=headers or {})
    return gh.GitHubClient(token, httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("url, expected", [("https://github.com/me/rag-bot", ("me", "rag-bot")), ("https://github.com/me/rag-bot.git", ("me", "rag-bot")),
                                           ("https://github.com/me/rag-bot/", ("me", "rag-bot"))])
def test_parse_repo_url(url, expected):
    assert gh.parse_repo_url(url) == expected


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a", "https://github.com/a/b/c", "https://github.com/a/b?x=1"])
def test_parse_repo_url_rejects_other_hosts_and_shapes(url):
    with pytest.raises(gh.GitHubError) as e:
        gh.parse_repo_url(url)
    assert e.value.code == "bad_repo"


def test_client_reads_a_commit_and_sends_the_token_only_in_the_header():
    seen: list = []
    info = make_client(token="ghp_SECRET", seen=seen).get_commit(REPO, "a1b2c3d4e5f6")
    assert (info.sha, info.files_changed, info.additions, info.deletions, info.parents) == (FULL, 1, 40, 2, 1)
    assert seen[0].url.path == "/repos/me/rag-bot/commits/a1b2c3d4e5f6" and "ghp_SECRET" not in str(seen[0].url)
    assert seen[0].headers["authorization"] == "Bearer ghp_SECRET"


def test_no_token_means_no_authorization_header():
    seen: list = []
    make_client(seen=seen).get_commit(REPO, "a1b2c3d4e5f6")
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize("status, headers, code", [(404, {}, "not_found"), (422, {}, "not_found"), (429, {}, "rate_limited"),
                                                   (403, {"x-ratelimit-remaining": "0"}, "rate_limited"), (401, {}, "bad_token"), (500, {}, "api_error")])
def test_client_errors_have_stable_codes(status, headers, code):
    with pytest.raises(gh.GitHubError) as e:
        make_client(status, {"message": "secret internal text"}, headers).get_commit(REPO, "a1b2c3d4e5f6")
    assert e.value.code == code and "secret internal text" not in e.value.message


def test_bad_sha_is_rejected_before_any_request():
    seen: list = []
    with pytest.raises(gh.GitHubError) as e:
        make_client(seen=seen).get_commit(REPO, "../../etc")
    assert e.value.code == "bad_sha" and seen == []


def test_network_failure_is_reported():
    def boom(req):
        raise httpx.ConnectError("x")
    with pytest.raises(gh.GitHubError) as e:
        gh.GitHubClient(None, httpx.Client(transport=httpx.MockTransport(boom))).get_commit(REPO, "a1b2c3d4e5f6")
    assert e.value.code == "network"


# ---------------- HTTP endpoint ----------------

@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    yield client
    app.dependency_overrides.pop(get_github, None)


def use(client_obj):
    app.dependency_overrides[get_github] = lambda: client_obj


def completed(c):
    ch = plan(c, project(c)["id"])
    r = c.post(f"/api/challenges/{ch['id']}/complete", json=EVIDENCE)
    assert r.status_code == 200, r.text
    assert r.json()["verification_status"] == "unverified"
    return ch["id"]


def test_verify_requires_login(client):
    assert client.post("/api/challenges/1/verify").status_code == 401


def test_a_real_matching_commit_verifies_and_stores_the_full_hash(c):
    cid = completed(c)
    use(make_client())
    r = c.post(f"/api/challenges/{cid}/verify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True and all(k["ok"] for k in body["checks"])
    assert body["challenge"]["verification_status"] == "verified" and body["challenge"]["commit_sha"] == FULL
    assert c.get(f"/api/challenges/{cid}").json()["verification_status"] == "verified"


def test_a_commit_with_a_different_message_stays_unverified(c):
    cid = completed(c)
    d = commit_json()
    d["commit"]["message"] = "Totally unrelated change"
    use(make_client(body=d))
    body = c.post(f"/api/challenges/{cid}/verify").json()
    assert body["verified"] is False and [k["name"] for k in body["checks"] if not k["ok"]] == ["Message matches"]
    assert body["challenge"]["verification_status"] == "unverified"


def test_an_old_commit_stays_unverified(c):
    cid = completed(c)
    d = commit_json()
    d["commit"]["committer"]["date"] = "2020-01-01T00:00:00Z"
    use(make_client(body=d))
    body = c.post(f"/api/challenges/{cid}/verify").json()
    assert body["verified"] is False and [k["name"] for k in body["checks"] if not k["ok"]] == ["Made on the day"]


def test_an_empty_commit_stays_unverified(c):
    cid = completed(c)
    use(make_client(body=commit_json(stats={"additions": 0, "deletions": 0}, files=[])))
    body = c.post(f"/api/challenges/{cid}/verify").json()
    assert body["verified"] is False and [k["name"] for k in body["checks"] if not k["ok"]] == ["Changes code"]


def test_a_commit_github_does_not_know_is_404_and_stays_unverified(c):
    cid = completed(c)
    use(make_client(404, {"message": "Not Found"}))
    r = c.post(f"/api/challenges/{cid}/verify")
    assert r.status_code == 404 and "no commit" in r.json()["detail"]
    assert c.get(f"/api/challenges/{cid}").json()["verification_status"] == "unverified"


def test_rate_limit_is_429(c):
    cid = completed(c)
    use(make_client(429, {}))
    assert c.post(f"/api/challenges/{cid}/verify").status_code == 429


def test_only_completed_challenges_can_be_verified(c):
    ch = plan(c, project(c)["id"])
    use(make_client())
    assert c.post(f"/api/challenges/{ch['id']}/verify").status_code == 422


def test_unknown_challenge_is_404(c):
    use(make_client())
    assert c.post("/api/challenges/9999/verify").status_code == 404


# ---------------- repo preview (project import) ----------------

README = "# My Bot\n\n[![CI](https://x/badge.svg)](https://x)\n\nA **RAG chatbot** that answers questions about [my docs](https://example.com/docs).\n\n## Setup\nrun it\n"


def repo_client(repo_status=200, readme_status=200, langs_status=200):
    def handler(req: httpx.Request):
        path = req.url.path
        if path.endswith("/languages"):
            return httpx.Response(langs_status, json={"Python": 9000, "HTML": 100, "TypeScript": 5000})
        if path.endswith("/readme"):
            return httpx.Response(readme_status, text=README)
        return httpx.Response(repo_status, json={"name": "rag-bot", "description": None, "topics": ["llm", "python"], "created_at": "2025-03-04T10:00:00Z"})
    return gh.GitHubClient(None, httpx.Client(transport=httpx.MockTransport(handler)))


def test_repo_preview_needs_login(client):
    assert client.post("/api/github/repo-preview", json={"repo_url": REPO}).status_code == 401


def test_repo_preview_suggests_fields_without_saving_anything(c):
    use(repo_client())
    r = c.post("/api/github/repo-preview", json={"repo_url": REPO})
    assert r.status_code == 200, r.text
    assert r.json() == {"title": "rag-bot", "description": "A RAG chatbot that answers questions about my docs.",
                        "tech_stack": ["Python", "TypeScript", "HTML", "llm"], "repo_url": REPO, "start_date": "2025-03-04", "readme_found": True}
    assert c.get("/api/projects").json() == [] or c.get("/api/projects").json().get("items", []) == []


def test_repo_preview_works_without_readme_or_languages(c):
    use(repo_client(readme_status=404, langs_status=404))
    r = c.post("/api/github/repo-preview", json={"repo_url": REPO}).json()
    assert r["description"] is None and r["readme_found"] is False and r["tech_stack"] == ["llm", "python"]


def test_repo_preview_unknown_repo_is_404_and_bad_url_is_422(c):
    use(repo_client(repo_status=404))
    assert c.post("/api/github/repo-preview", json={"repo_url": REPO}).status_code == 404
    assert c.post("/api/github/repo-preview", json={"repo_url": "https://evil.com/a/b"}).status_code == 422
