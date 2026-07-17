#!/usr/bin/env python3
"""Shared GitHub REST API glue for aep/pipelines/*.py.

Used by dispatch_to_agent.py, audit_loop.py, and dispatch_publish.py. The
only network calls anywhere in this module are to the GitHub REST API
(issues/comments/search) — never to an LLM provider, so every caller stays
compliant with aep/policies/no-external-llm-policy.md regardless of which
agent ends up doing the actual work.

IMPORTANT: comments posted with the default Actions GITHUB_TOKEN do NOT
re-trigger other workflows (GitHub's loop-prevention rule) — an `@claude`
comment posted that way would silently fail to wake up aep-claude-manual.yml.
Every caller here must pass a real PAT (COPILOT_DISPATCH_PAT), never the
default token, when the point of the comment is to trigger a new run.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

QUOTA_HINT_KEYWORDS = ("quota", "premium request", "rate limit", "limit exceeded", "insufficient")


def github_request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {method} {url} -> {e.code}: {detail}") from e


def create_issue(title: str, body: str, token: str, repo: str) -> dict:
    return github_request("POST", f"https://api.github.com/repos/{repo}/issues", token, {"title": title, "body": body})


def assign_to_copilot(issue_number: int, token: str, repo: str) -> None:
    github_request(
        "PATCH",
        f"https://api.github.com/repos/{repo}/issues/{issue_number}",
        token,
        {"assignees": ["copilot-swe-agent[bot]"]},
    )


def comment(issue_or_pr_number: int, body: str, token: str, repo: str) -> dict:
    """Issues and PRs share the same comments endpoint in the GitHub API."""
    return github_request(
        "POST",
        f"https://api.github.com/repos/{repo}/issues/{issue_or_pr_number}/comments",
        token,
        {"body": body},
    )


def comment_at_claude(issue_or_pr_number: int, note: str, token: str, repo: str) -> dict:
    return comment(issue_or_pr_number, f"@claude {note}", token, repo)


def list_comments(issue_or_pr_number: int, token: str, repo: str) -> list:
    return github_request(
        "GET", f"https://api.github.com/repos/{repo}/issues/{issue_or_pr_number}/comments", token
    )


def find_open_item_for_target(target_dir: str, token: str, repo: str) -> dict | None:
    """Best-effort duplicate check via the search API — see the caller's docstring
    for the known indexing-lag caveat; this is a soft guard, not a hard lock."""
    query = f'repo:{repo} is:open "{target_dir}" in:title,body'
    url = "https://api.github.com/search/issues?q=" + urllib.parse.quote(query)
    result = github_request("GET", url, token)
    items = result.get("items", [])
    return items[0] if items else None


def looks_like_quota_exhaustion(error_message: str) -> bool:
    lowered = error_message.lower()
    return any(kw in lowered for kw in QUOTA_HINT_KEYWORDS)
