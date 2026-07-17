#!/usr/bin/env python3
"""Dispatch a 'sync this merged article to Notion' task — the actual
publisher stage, triggered once a human has approved an article by merging
its PR (merge = the human-approval signal per aep/README.md's constitution).

Deterministic scripts under aep/pipelines/ can never call an MCP tool
themselves — MCP tools only exist inside an agent's own tool-use context
(a Claude Code or Copilot session), not a plain Python process. So "wiring
the Notion integration" can only ever mean dispatching an agent turn that
has Notion MCP access, the same mechanism used to dispatch the writer stage
— never a raw Notion API call embedded here with a stored secret.
"""
import argparse
import json
import os
import pathlib

import github_api

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def build_publish_issue(article_dir: pathlib.Path) -> dict:
    publish_draft = json.loads((article_dir / "publish-draft.json").read_text(encoding="utf-8"))
    title = publish_draft.get("title", article_dir.name)
    rel_dir = article_dir.relative_to(REPO_ROOT)

    issue_title = f"[AEP/publish] Sync to Notion: {title}"
    body = f"""\
This issue was opened automatically because a PR merging `{rel_dir}/` into
main was just approved by a human (merge = the approval signal — see
aep/README.md's constitution: "human approval before publication").

## Your task
Follow `aep/prompts/publisher.md` to sync this article to Notion using the
Notion MCP tools available to you, with:
- `aep/publisher/notion-page-template.md` as the page body template
- `aep/publisher/notion-mapping.json` as the field mapping
- `{rel_dir / 'publish-draft.json'}`'s `external_id` (`{publish_draft.get('external_id', '')}`)
  for an **idempotent upsert** — search for an existing Notion page with this
  external_id first; update it if found, create only if not. Never create a
  duplicate page if this dispatch runs more than once for the same article.

Once the Notion page is live, open a small follow-up PR updating
`{rel_dir / 'publish-draft.json'}`'s `status` field to `"Ready to Publish"`
— don't push directly to main; every change here goes through a PR, even a
bookkeeping update like this one.

## Source article
- Article: `{rel_dir / 'article.md'}`
- Publish draft: `{rel_dir / 'publish-draft.json'}`
"""
    return {"title": issue_title, "body": body, "target_dir": str(rel_dir)}


def dispatch_publish(article_dir_str: str, dry_run: bool) -> None:
    article_dir = REPO_ROOT / article_dir_str
    publish_draft_path = article_dir / "publish-draft.json"
    if not publish_draft_path.exists():
        print(f"skip: {article_dir_str} has no publish-draft.json")
        return

    publish_draft = json.loads(publish_draft_path.read_text(encoding="utf-8"))
    status = publish_draft.get("status")
    if status != "Draft - Pending Human Approval":
        print(f"skip: {article_dir_str}'s publish-draft.json status is {status!r}, not pending approval")
        return

    issue = build_publish_issue(article_dir)

    if dry_run:
        print("--- DRY RUN ---")
        print(f"title: {issue['title']}")
        print(issue["body"])
        return

    token = os.environ.get("COPILOT_DISPATCH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise RuntimeError("COPILOT_DISPATCH_PAT and GITHUB_REPOSITORY must be set (use --dry-run to preview).")

    existing = github_api.find_open_item_for_target(issue["target_dir"], token, repo)
    if existing:
        print(f"An open issue/PR already targets `{issue['target_dir']}`: {existing['html_url']} — skipping.")
        return

    created = github_api.create_issue(issue["title"], issue["body"], token, repo)
    issue_number = created["number"]
    print(f"Created issue #{issue_number}: {created['html_url']}")

    try:
        github_api.assign_to_copilot(issue_number, token, repo)
        print("Assigned to copilot-swe-agent[bot]")
    except RuntimeError as exc:
        reason = "premium-request quota likely exhausted" if github_api.looks_like_quota_exhaustion(str(exc)) else "assignment failed"
        print(f"Copilot dispatch failed ({reason}): {exc}")
        note = (
            f"Copilot coding agent could not take this issue ({reason}). Please pick it up instead — "
            "follow aep/prompts/publisher.md using the Notion MCP tools available to you."
        )
        comment = github_api.comment_at_claude(issue_number, note, token, repo)
        print(f"Posted fallback comment: {comment['html_url']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch a Notion-publish task for a merged, human-approved article.")
    parser.add_argument("article_dirs", nargs="+", help="Repo-relative article dirs, e.g. articles/mcp-deep-dive/part-02")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for d in args.article_dirs:
        dispatch_publish(d, args.dry_run)


if __name__ == "__main__":
    main()
