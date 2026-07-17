#!/usr/bin/env python3
"""Enforced audit-retry loop for articles/** PRs.

aep-article-check.yml already runs validate_article.py as a required status
check on every PR touching articles/** — that tells you pass/fail, once.
This script is the loop that was missing: when it fails, automatically post
an `@claude` comment with the exact failure output so the agent that opened
the PR gets a chance to fix it without a human having to notice and ask —
up to a fixed retry budget. Past that budget it stops nagging and flags for
a human instead of retrying forever (an unenforced loop is just a runaway
cost/noise risk, not a real guardrail).
"""
import argparse
import os
import pathlib
import subprocess
import sys

import github_api

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MARKER = "<!-- aep-audit-loop -->"
MAX_ATTEMPTS = 3


def run_validate(article_dir: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["python3", "aep/pipelines/validate_article.py", article_dir],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def count_prior_attempts(pr_number: int, token: str, repo: str) -> int:
    comments = github_api.list_comments(pr_number, token, repo)
    return sum(1 for c in comments if MARKER in c.get("body", ""))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run validate_article.py on changed dirs; auto-retry via @claude on failure, up to a retry cap."
    )
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("article_dirs", nargs="+")
    args = parser.parse_args()

    token = os.environ.get("COPILOT_DISPATCH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    have_creds = bool(token and repo)
    if not have_creds:
        print("COPILOT_DISPATCH_PAT/GITHUB_REPOSITORY not set — running validate_article.py only, no comment loop.")

    failures = {}
    for d in args.article_dirs:
        ok, output = run_validate(d)
        if not ok:
            failures[d] = output

    if not failures:
        print("All changed article dirs pass validate_article.py.")
        return

    print("validate_article.py failures:\n" + "\n\n".join(f"### {d}\n{out}" for d, out in failures.items()))

    if not have_creds:
        sys.exit(1)

    attempts = count_prior_attempts(args.pr_number, token, repo)
    if attempts >= MAX_ATTEMPTS:
        github_api.comment(
            args.pr_number,
            f"{MARKER}\n**Audit loop stopping after {attempts} automated attempts.** "
            "`validate_article.py` still fails — see the latest `aep-article-check` run for "
            "details. This needs a human to look at it rather than another automated retry.",
            token, repo,
        )
        print(f"Hit max attempts ({MAX_ATTEMPTS}) — flagged for human attention, not retrying further.")
        sys.exit(1)

    failure_text = "\n\n".join(f"{d}:\n{out}" for d, out in failures.items())[:5000]
    note = (
        f"{MARKER}\n"
        f"**Automated audit loop, attempt {attempts + 1}/{MAX_ATTEMPTS}.** "
        f"`validate_article.py` failed on this PR:\n\n```\n{failure_text}\n```\n\n"
        "Please fix these and push to this PR. Re-run "
        "`python3 aep/pipelines/validate_article.py <dir>` yourself before pushing "
        "so you're not relying on this loop to find the next gap — it's a backstop, "
        "not the primary review."
    )
    github_api.comment_at_claude(args.pr_number, note, token, repo)
    print(f"Posted fix-it comment (attempt {attempts + 1}/{MAX_ATTEMPTS}).")
    sys.exit(1)


if __name__ == "__main__":
    main()
