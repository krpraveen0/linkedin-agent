#!/usr/bin/env python3
"""Hand the latest deterministic AEP run off to a coding agent: Copilot first,
Claude Code as fallback if Copilot can't take the job (e.g. premium-request
quota exhausted on the Copilot plan).

Flow:
1. Create a GitHub issue describing the top-ranked topic, target folder, and
   the exact prompt contracts + deliverables to follow.
2. Try to assign it to Copilot's cloud coding agent via the Issues API.
3. If assignment fails for any reason (quota exhaustion, auth, API change),
   post an `@claude` comment on the same issue instead. That comment is a
   normal `issue_comment` event, which triggers aep-claude-manual.yml
   reliably (unlike a `schedule:` trigger — see
   https://github.com/anthropics/claude-code-action/issues/814 — which is
   why this fallback goes through a comment rather than invoking Claude
   Code directly inside this same scheduled job).

The only network calls here are to the GitHub REST API (issue create/assign/
comment) — never to an LLM provider, so this stays compliant with
aep/policies/no-external-llm-policy.md regardless of which agent ends up
doing the work.
"""
import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AEP_DIR = REPO_ROOT / "aep"
COPILOT_ASSIGNEE = "copilot-swe-agent[bot]"

QUOTA_HINT_KEYWORDS = ("quota", "premium request", "rate limit", "limit exceeded", "insufficient")


def load_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_run_dir(mode: str) -> pathlib.Path:
    pointer = load_json(AEP_DIR / "out" / mode / "last-run.json")
    return AEP_DIR / "out" / mode / pointer["latest_run_id"]


def build_issue(mode: str, run_dir: pathlib.Path) -> dict:
    research_bundle = load_json(run_dir / "research-bundle.json")
    ranked_topics = load_json(run_dir / "ranked-topics.json")["ranked_topics"]
    run_summary = load_json(run_dir / "run-summary.json")
    top = ranked_topics[0]
    rel_run_dir = run_dir.relative_to(REPO_ROOT)
    target = run_summary.get("target_article", {})
    target_dir = target.get("dir", "articles/<topic-slug>")

    references = "\n".join(
        f"- {url}" for url in research_bundle["official_references"] + research_bundle.get("supporting_references", [])
    )
    claims = "\n".join(f"- {c['statement']}" for c in research_bundle.get("claims", []))

    if target.get("kind") == "series-continuation":
        target_note = (
            f"Proposed as **part {target['series_part']}** of the `{target['series_name']}` series "
            f"(\"{target.get('series_title', '')}\") — verify this is still correct against "
            f"`articles/{target['series_name']}/` before committing to it."
        )
    else:
        target_note = "Proposed as a **standalone article** (no active series had parts remaining)."

    title = f"[AEP/{mode}] Draft article: {top['topic']}"
    body = f"""\
This issue was opened automatically by the `{mode}` AEP pipeline run.

**Topic:** {top['topic']} (overall_score={top['overall_score']})
**Target folder:** `{target_dir}/` — {target_note}

## Your task
Follow these prompt contracts, in order, from this repository:
1. `aep/prompts/research.md` — expand `{rel_run_dir}/research-bundle.json` if needed;
   every claim must keep reference URLs.
2. `aep/prompts/writer.md` — draft the article **and commit the full deliverable set**,
   not just prose. This is what "publish-ready" requires, all under `{target_dir}/`:
   - `article.md` — hero image embed, content, an embedded topic-specific mermaid
     diagram, real code snippets, a mini-project section, trade-offs, references
   - `assets/hero.png` — generate via `python3 aep/pipelines/generate_hero_image.py
     --title "..." --out {target_dir}/assets/hero.png` (or hand-author an SVG).
     Never call an external image-generation API.
   - `assets/diagrams/architecture.mmd` — topic-specific, not generic
   - `project/` — a real, runnable mini-project with `project/README.md` and actual
     source files (see `aep/prompts/production-engineering.md`)
   - `research-bundle.json`, `publish-draft.json` — matching
     `aep/schemas/research-bundle.schema.json` / `publish-draft.schema.json`,
     with `article_path`/`hero_image_path`/`diagram_paths`/`project_path` pointing
     at files that actually exist
3. `aep/prompts/production-engineering.md` — run the mini-project for real, capture
   real command output as evidence; never claim execution without it.
4. `aep/prompts/technical-auditor.md` and `aep/prompts/platform-auditor.md` — self-check
   the draft against these before opening the PR.

Constitution rules (`aep/README.md`): never publish unexecuted code, prefer official
docs, every claim referenced, human approval required before publication — this issue
only authorizes a **draft PR**, not publishing.

## Starting material (from this run)
Research bundle: `{rel_run_dir / 'research-bundle.json'}`
Ranked topics: `{rel_run_dir / 'ranked-topics.json'}`
Hero image preview (baseline only, feel free to improve): `{rel_run_dir / 'hero_preview.png'}`
Notion draft template: `aep/publisher/notion-page-template.md`

Official references so far:
{references or '(none captured — verify against official docs before drafting)'}

Claims so far:
{claims or '(none captured — build these out per aep/prompts/research.md)'}

## Before opening the PR
Run `python3 aep/pipelines/validate_article.py {target_dir}` — this is the exact
check CI (`aep-article-check.yml`) runs against your PR. Fix everything it flags
first; don't rely on CI to find gaps for you.

If this is a series continuation, also update `articles/{target.get('series_name', '')}/README.md`
with the new part.
"""
    return {"title": title, "body": body}


def _github_request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
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
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {method} {url} -> {e.code}: {detail}") from e


def create_issue(title: str, body: str, token: str, repo: str) -> dict:
    return _github_request("POST", f"https://api.github.com/repos/{repo}/issues", token, {"title": title, "body": body})


def assign_to_copilot(issue_number: int, token: str, repo: str) -> None:
    _github_request(
        "PATCH",
        f"https://api.github.com/repos/{repo}/issues/{issue_number}",
        token,
        {"assignees": [COPILOT_ASSIGNEE]},
    )


def comment_at_claude(issue_number: int, note: str, token: str, repo: str) -> dict:
    body = f"@claude {note}"
    return _github_request(
        "POST",
        f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
        token,
        {"body": body},
    )


def looks_like_quota_exhaustion(error_message: str) -> bool:
    lowered = error_message.lower()
    return any(kw in lowered for kw in QUOTA_HINT_KEYWORDS)


def dispatch(mode: str, dry_run: bool, simulate_copilot_failure: bool = False) -> None:
    run_dir = latest_run_dir(mode)
    issue = build_issue(mode, run_dir)

    if dry_run:
        print("--- DRY RUN: would create issue, try Copilot, fall back to @claude on failure ---")
        print(f"title: {issue['title']}")
        print(issue["body"])
        if simulate_copilot_failure:
            print("--- simulated Copilot failure -> fallback comment would be ---")
            print(f"@claude {_fallback_note('simulated quota exhaustion for --dry-run testing')}")
        return

    token = os.environ.get("COPILOT_DISPATCH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise RuntimeError(
            "COPILOT_DISPATCH_PAT and GITHUB_REPOSITORY must be set to dispatch for real "
            "(use --dry-run to preview without them)."
        )

    created = create_issue(issue["title"], issue["body"], token, repo)
    issue_number = created["number"]
    print(f"Created issue #{issue_number}: {created['html_url']}")

    if simulate_copilot_failure:
        assign_error = "simulated failure via --simulate-copilot-failure"
    else:
        try:
            assign_to_copilot(issue_number, token, repo)
            print(f"Assigned to {COPILOT_ASSIGNEE}")
            return
        except RuntimeError as exc:
            assign_error = str(exc)

    reason = "premium-request quota likely exhausted" if looks_like_quota_exhaustion(assign_error) else "assignment failed"
    print(f"Copilot dispatch failed ({reason}): {assign_error}")
    print("Falling back to Claude Code via @claude comment...")
    comment = comment_at_claude(issue_number, _fallback_note(reason), token, repo)
    print(f"Posted fallback comment: {comment['html_url']}")


def _fallback_note(reason: str) -> str:
    return (
        f"Copilot coding agent could not take this issue ({reason}). Please pick it up instead — "
        "the full task, target folder, and required deliverables are in the issue description above. "
        "Follow aep/prompts/writer.md and run `python3 aep/pipelines/validate_article.py <target-dir>` "
        "before opening the PR."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch latest AEP run to Copilot, falling back to Claude Code.")
    parser.add_argument("--mode", choices=["morning", "evening"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print instead of calling the GitHub API")
    parser.add_argument(
        "--simulate-copilot-failure",
        action="store_true",
        help="Force the Claude fallback path (for testing the fallback without waiting on real quota exhaustion)",
    )
    args = parser.parse_args()
    dispatch(args.mode, args.dry_run, args.simulate_copilot_failure)


if __name__ == "__main__":
    main()
