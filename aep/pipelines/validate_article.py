#!/usr/bin/env python3
"""Publishing-readiness gate for a finished articles/** folder.

Unlike aep/pipelines/validate_artifacts.py (which checks the deterministic
scratch pipeline output under aep/out/), this validates the REAL article an
agent (Copilot/Claude/opencode) produced: hero image, topic-specific
diagram(s), code snippets in the article body, a non-empty runnable
mini-project with a README, and a publish-draft.json whose declared paths
all actually exist on disk. "Never publish unexecuted code" only means
something if this is enforced mechanically, not just requested in a prompt.
"""
import argparse
import json
import pathlib
import re
import sys
from typing import List

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _display_path(p: pathlib.Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def check_publish_draft(article_dir: pathlib.Path) -> List[str]:
    errors: List[str] = []
    draft_path = article_dir / "publish-draft.json"
    if not draft_path.exists():
        return [f"missing {draft_path.relative_to(REPO_ROOT)}"]

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    required = [
        "external_id", "title", "status", "body_path", "references",
        "human_approval_required", "article_path", "hero_image_path",
        "diagram_paths", "project_path",
    ]
    missing = [f for f in required if f not in draft]
    if missing:
        errors.append(f"publish-draft.json missing required fields: {missing}")
        return errors

    if draft["status"] not in ("Draft - Pending Human Approval", "Ready to Publish"):
        errors.append(f"invalid status: {draft['status']}")
    if draft["human_approval_required"] is not True:
        errors.append("human_approval_required must be true")
    if not draft["references"]:
        errors.append("references must be non-empty")
    if not draft["diagram_paths"]:
        errors.append("diagram_paths must be non-empty")

    path_fields = {
        "article_path": draft["article_path"],
        "hero_image_path": draft["hero_image_path"],
        "project_path": draft["project_path"],
    }
    for field, rel_path in path_fields.items():
        if not (REPO_ROOT / rel_path).exists():
            errors.append(f"{field} declares '{rel_path}' but that path does not exist")
    for rel_path in draft["diagram_paths"]:
        if not (REPO_ROOT / rel_path).exists():
            errors.append(f"diagram_paths entry '{rel_path}' does not exist")

    return errors


def check_article_content(article_dir: pathlib.Path) -> List[str]:
    errors: List[str] = []
    article_path = article_dir / "article.md"
    if not article_path.exists():
        return [f"missing {article_path.relative_to(REPO_ROOT)}"]

    text = article_path.read_text(encoding="utf-8")

    if not re.search(r"!\[[^\]]*\]\([^)]+\)", text):
        errors.append("article.md has no image embed (hero image must be referenced in the body)")

    has_mermaid_fence = "```mermaid" in text
    has_diagram_link = bool(re.search(r"\.mmd\b", text))
    if not (has_mermaid_fence or has_diagram_link):
        errors.append("article.md references no diagram (neither a ```mermaid fence nor a .mmd link)")

    code_fences = re.findall(r"```(?!mermaid)\w*\n.*?```", text, flags=re.S)
    if not code_fences:
        errors.append("article.md has no non-diagram code snippets")

    if len(text.split()) < 300:
        errors.append(f"article.md is too short ({len(text.split())} words) to be publish-ready")

    return errors


def check_hero_image(article_dir: pathlib.Path) -> List[str]:
    hero_dir = article_dir / "assets"
    candidates = list(hero_dir.glob("hero.*")) if hero_dir.exists() else []
    if not candidates:
        return [f"no assets/hero.* found under {article_dir.relative_to(REPO_ROOT)}"]
    empty = [c for c in candidates if c.stat().st_size == 0]
    if empty:
        return [f"hero image file(s) are empty: {[str(c) for c in empty]}"]
    return []


def check_project_folder(article_dir: pathlib.Path) -> List[str]:
    project_dir = article_dir / "project"
    if not project_dir.exists() or not project_dir.is_dir():
        return [f"missing mini-project folder at {project_dir.relative_to(REPO_ROOT)}"]

    files = [p for p in project_dir.rglob("*") if p.is_file()]
    if not files:
        return [f"{project_dir.relative_to(REPO_ROOT)} exists but is empty"]

    if not (project_dir / "README.md").exists():
        return [f"{project_dir.relative_to(REPO_ROOT)} has no README.md explaining how to run it"]

    code_files = [p for p in files if p.suffix not in {".md", ""} and p.name != "README.md"]
    if not code_files:
        return [f"{project_dir.relative_to(REPO_ROOT)} has no source files, only docs"]

    return []


def validate_article(article_dir: pathlib.Path) -> List[str]:
    errors: List[str] = []
    if not article_dir.exists():
        return [f"article directory does not exist: {article_dir}"]
    errors += check_publish_draft(article_dir)
    errors += check_article_content(article_dir)
    errors += check_hero_image(article_dir)
    errors += check_project_folder(article_dir)
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a finished articles/** folder is publish-ready.")
    parser.add_argument("article_dir", type=pathlib.Path, help="e.g. articles/mcp-deep-dive/part-02 or articles/my-standalone-slug")
    args = parser.parse_args()

    target = args.article_dir if args.article_dir.is_absolute() else REPO_ROOT / args.article_dir
    errors = validate_article(target)

    if errors:
        print(f"NOT publish-ready: {_display_path(target)}")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print(f"publish-ready: {_display_path(target)}")


if __name__ == "__main__":
    main()
