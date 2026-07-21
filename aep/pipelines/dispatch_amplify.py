#!/usr/bin/env python3
"""Dispatch a 'draft a LinkedIn post for this article' task — the
amplification stage, triggered once the publisher stage has confirmed the
Notion sync and flipped publish-draft.json's status to "Ready to Publish"
(aep/prompts/publisher.md's step 6). Mirrors dispatch_publish.py's shape:
this workflow fires on every merge touching articles/**, so the status
check below is what decides whether a given merge is actually the trigger
event, not the workflow itself.

Deterministic scripts under aep/pipelines/ never call an LLM or post to
LinkedIn directly — no LinkedIn API credential is stored in this repo. This
only ever dispatches an agent turn (aep/prompts/amplify.md) that drafts a
linkedin-post.json for a human to review and post themselves.
"""
import argparse
import json
import os
import pathlib

import github_api

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def build_amplify_issue(article_dir: pathlib.Path) -> dict:
    publish_draft = json.loads((article_dir / "publish-draft.json").read_text(encoding="utf-8"))
    title = publish_draft.get("title", article_dir.name)
    rel_dir = article_dir.relative_to(REPO_ROOT)

    issue_title = f"[AEP/amplify] Draft LinkedIn post: {title}"
    body = f"""\
This issue was opened automatically because `{rel_dir / 'publish-draft.json'}`'s
`status` was just confirmed as `"Ready to Publish"` — the Notion sync
succeeded (aep/prompts/publisher.md), so it's time to draft the LinkedIn
amplification for this article.

## Your task
Follow `aep/prompts/amplify.md` to draft one LinkedIn post for this article,
applying `aep/prompts/brand-voice.md`'s tone rules and
`.agents/skills/writing-linkedin-posts/SKILL.md`'s format craft (hook
patterns only — every claim must come from this article's own evidence).

Save `{rel_dir / 'linkedin-post.json'}` matching
`aep/schemas/linkedin-post.schema.json`, with `status: "Draft - Pending
Human Approval"` and `external_id` `{publish_draft.get('external_id', '')}`.
Open a PR with it — don't push directly to main. This stage drafts only; a
human posts it to LinkedIn themselves and flips `status` to `"Posted"` in a
follow-up PR.

## Source article
- Article: `{rel_dir / 'article.md'}`
- Research bundle: `{rel_dir / 'research-bundle.json'}`
- Publish draft: `{rel_dir / 'publish-draft.json'}`
"""
    return {"title": issue_title, "body": body, "target_dir": str(rel_dir)}


def dispatch_amplify(article_dir_str: str, dry_run: bool) -> None:
    article_dir = REPO_ROOT / article_dir_str
    publish_draft_path = article_dir / "publish-draft.json"
    if not publish_draft_path.exists():
        print(f"skip: {article_dir_str} has no publish-draft.json")
        return

    publish_draft = json.loads(publish_draft_path.read_text(encoding="utf-8"))
    status = publish_draft.get("status")
    if status != "Ready to Publish":
        print(f"skip: {article_dir_str}'s publish-draft.json status is {status!r}, not Ready to Publish yet")
        return

    if (article_dir / "linkedin-post.json").exists():
        print(f"skip: {article_dir_str} already has linkedin-post.json")
        return

    issue = build_amplify_issue(article_dir)

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
            "follow aep/prompts/amplify.md."
        )
        comment = github_api.comment_at_claude(issue_number, note, token, repo)
        print(f"Posted fallback comment: {comment['html_url']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch a LinkedIn-amplification task for a Notion-synced article.")
    parser.add_argument("article_dirs", nargs="+", help="Repo-relative article dirs, e.g. articles/mcp-deep-dive/part-02")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for d in args.article_dirs:
        dispatch_amplify(d, args.dry_run)


if __name__ == "__main__":
    main()
