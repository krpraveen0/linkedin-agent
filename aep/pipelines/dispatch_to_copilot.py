#!/usr/bin/env python3
"""Hand the latest deterministic AEP run off to GitHub Copilot coding agent.

Creates a GitHub issue describing the top-ranked topic and the exact prompt
contracts to follow, then assigns it to Copilot's cloud agent via the Issues
API. This is the only network call in aep/pipelines/ — it talks to the
GitHub API only (issue creation + assignment), never to an LLM provider, so
it stays compliant with aep/policies/no-external-llm-policy.md. The actual
writing happens inside GitHub's own Copilot coding agent infrastructure,
asynchronously, and lands as a PR for human review.
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


def load_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_run_dir(mode: str) -> pathlib.Path:
    pointer = load_json(AEP_DIR / "out" / mode / "last-run.json")
    return AEP_DIR / "out" / mode / pointer["latest_run_id"]


def build_issue(mode: str, run_dir: pathlib.Path) -> dict:
    research_bundle = load_json(run_dir / "research-bundle.json")
    ranked_topics = load_json(run_dir / "ranked-topics.json")["ranked_topics"]
    top = ranked_topics[0]
    rel_run_dir = run_dir.relative_to(REPO_ROOT)

    references = "\n".join(
        f"- {url}" for url in research_bundle["official_references"] + research_bundle.get("supporting_references", [])
    )
    claims = "\n".join(f"- {c['statement']}" for c in research_bundle.get("claims", []))

    title = f"[AEP/{mode}] Draft article: {top['topic']}"
    body = f"""\
This issue was opened automatically by the `{mode}` AEP pipeline run.

**Topic:** {top['topic']} (overall_score={top['overall_score']})

## Your task
Follow these prompt contracts, in order, from this repository:
1. `aep/prompts/research.md` — expand `{rel_run_dir}/research-bundle.json` if needed;
   every claim must keep reference URLs.
2. `aep/prompts/writer.md` — draft the article. Explain architecture/implementation,
   reference every technical claim, keep status `Draft - Pending Human Approval`.
3. `aep/prompts/production-engineering.md` — if you add a build/PoC, include real
   command output as evidence; never claim execution without it.
4. `aep/prompts/technical-auditor.md` and `aep/prompts/platform-auditor.md` — self-check
   the draft against these before opening the PR.

Constitution rules (`aep/README.md`): never publish unexecuted code, prefer official
docs, every claim referenced, human approval required before publication — this issue
only authorizes a **draft PR**, not publishing.

## Starting material (from this run)
Research bundle: `{rel_run_dir / 'research-bundle.json'}`
Ranked topics: `{rel_run_dir / 'ranked-topics.json'}`
Notion draft template: `aep/publisher/notion-page-template.md`

Official references so far:
{references or '(none captured — verify against official docs before drafting)'}

Claims so far:
{claims or '(none captured — build these out per aep/prompts/research.md)'}

## Output
Open a PR with the article draft and update `{rel_run_dir / 'publish-draft.json'}`
to match `aep/schemas/publish-draft.schema.json`. Keep `human_approval_required: true`
and status `Draft - Pending Human Approval`.
"""
    return {"title": title, "body": body}


def dispatch(mode: str, dry_run: bool) -> None:
    run_dir = latest_run_dir(mode)
    issue = build_issue(mode, run_dir)

    if dry_run:
        print("--- DRY RUN: would create+assign this issue ---")
        print(f"title: {issue['title']}")
        print(issue["body"])
        return

    token = os.environ.get("COPILOT_DISPATCH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise RuntimeError(
            "COPILOT_DISPATCH_PAT and GITHUB_REPOSITORY must be set to dispatch for real "
            "(use --dry-run to preview without them)."
        )

    payload = {
        "title": issue["title"],
        "body": issue["body"],
        "assignees": [COPILOT_ASSIGNEE],
    }
    req = urllib.request.Request(
        url=f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API error {e.code}: {e.read().decode('utf-8', 'replace')}") from e

    print(f"Created issue #{result['number']} assigned to {COPILOT_ASSIGNEE}: {result['html_url']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch latest AEP run to Copilot coding agent.")
    parser.add_argument("--mode", choices=["morning", "evening"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print the issue instead of creating it")
    args = parser.parse_args()
    dispatch(args.mode, args.dry_run)


if __name__ == "__main__":
    main()
