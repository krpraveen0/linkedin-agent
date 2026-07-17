#!/usr/bin/env python3
"""Publishing-readiness gate for a finished articles/** folder.

Unlike aep/pipelines/validate_artifacts.py (which checks the deterministic
scratch pipeline output under aep/out/), this validates the REAL article an
agent (Copilot/Claude/opencode) produced: hero image, topic-specific
diagram(s), code snippets in the article body, a non-empty runnable
mini-project with a README, and a publish-draft.json whose declared paths
all actually exist on disk. "Never publish unexecuted code" only means
something if this is enforced mechanically, not just requested in a prompt —
so this also actually runs project/'s documented command (check_execution),
lints for a fixed list of AI-tell phrases (check_style), and requires a
concept-infographic once the article enumerates 3+ comparable items instead
of leaving them as prose bullets (check_infographic).
"""
import argparse
import json
import pathlib
import re
import shlex
import subprocess
import sys
from typing import List

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Fixed list of AI-tell phrases. This is a cheap, deterministic backstop —
# it will not catch every generic-sounding sentence, and it will not flag
# every draft that reads as AI-written. It exists to make the most common,
# easily-avoided tells mechanically impossible to ship, per the voice rules
# in aep/prompts/writer.md. The real judgment call is the platform-auditor
# agent's job (aep/prompts/platform-auditor.md).
AI_TELL_PATTERNS = [
    r"in today'?s fast-paced",
    r"in the ever-evolving",
    r"unlock(?:ing)? the (?:full )?potential",
    r"game[- ]changing",
    r"game changer",
    r"revolution(?:ize|izing|ary)",
    r"seamless(?:ly)?",
    r"\bdive into\b",
    r"\bdelve into\b",
    r"\bas an ai\b",
    r"^in conclusion",
    r"let'?s explore",
    r"it'?s important to note",
    r"cutting[- ]edge",
    r"as i reflect on my journey",
    r"harness(?:ing)? the power",
    r"here are \w+ key points to consider",
]

STALE_EXECUTION_PHRASES = [
    "not executed", "wasn't executed", "was not executed", "did not execute",
    "hasn't been run", "has not been run", "not been executed",
]


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


def check_topic_research_decision(article_dir: pathlib.Path) -> List[str]:
    """Mechanical teeth for aep/prompts/trend-research-agent.md: the deterministic
    pre-filter (fetch_trend_signals.py) has no judgment, so a real research pass
    over the shortlist is required before writing — this is what makes that
    requirement enforced rather than a prompt suggestion that's easy to skip."""
    path = article_dir / "topic-research-decision.json"
    if not path.exists():
        return [
            f"missing {path.relative_to(REPO_ROOT)} — aep/prompts/trend-research-agent.md "
            "must run before writing; the deterministic topic pre-filter has no judgment "
            "of its own and its pick must be reviewed, not taken on faith"
        ]
    try:
        decision = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"topic-research-decision.json is not valid JSON: {e}"]

    errors: List[str] = []
    required = ["topic_confirmed", "final_topic", "confidence", "rationale", "sources_checked", "decided_at"]
    missing = [f for f in required if f not in decision]
    if missing:
        errors.append(f"topic-research-decision.json missing required fields: {missing}")
        return errors
    if not decision["sources_checked"]:
        errors.append("topic-research-decision.json's sources_checked must be non-empty — real URLs actually reviewed")
    if decision["confidence"] not in ("low", "medium", "high"):
        errors.append(f"topic-research-decision.json has invalid confidence: {decision['confidence']!r}")
    return errors


def check_research_bundle(article_dir: pathlib.Path) -> List[str]:
    path = article_dir / "research-bundle.json"
    if not path.exists():
        return [f"missing {path.relative_to(REPO_ROOT)}"]
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"research-bundle.json is not valid JSON: {e}"]

    errors: List[str] = []
    scan = bundle.get("competitive_scan")
    if not scan:
        errors.append(
            "research-bundle.json has no competitive_scan entries — "
            "aep/prompts/research.md requires 2-3 existing published pieces "
            "on this topic, each with a stated differentiation"
        )
    else:
        for i, entry in enumerate(scan):
            if not entry.get("source_url") or not entry.get("differentiation"):
                errors.append(
                    f"competitive_scan[{i}] is missing source_url or differentiation"
                )
    return errors


def check_style(article_dir: pathlib.Path) -> List[str]:
    article_path = article_dir / "article.md"
    if not article_path.exists():
        return []
    text = article_path.read_text(encoding="utf-8")
    # Strip fenced code blocks first so phrases inside real code/comments
    # (e.g. a docstring quoting a bad example) aren't mistaken for prose.
    text_no_code = re.sub(r"```.*?```", "", text, flags=re.S)

    hits = [p for p in AI_TELL_PATTERNS if re.search(p, text_no_code, flags=re.I | re.M)]
    if hits:
        return [
            "article.md contains AI-tell phrasing that aep/prompts/writer.md's "
            f"voice rules ban (matched: {hits}) — rewrite those sections in a "
            "direct, specific voice"
        ]
    return []


def check_infographic(article_dir: pathlib.Path) -> List[str]:
    article_path = article_dir / "article.md"
    if not article_path.exists():
        return []
    text = article_path.read_text(encoding="utf-8")
    text_no_code = re.sub(r"```.*?```", "", text, flags=re.S)

    bullet_items = re.findall(r"^\s*[-*]\s+\*\*[^*]+\*\*", text_no_code, flags=re.M)
    numbered_items = re.findall(r"^\s*\d+\.\s+\*\*[^*]+\*\*", text_no_code, flags=re.M)
    concept_count = len(bullet_items) + len(numbered_items)

    if concept_count < 3:
        return []

    assets_dir = article_dir / "assets"
    diagram_dir = assets_dir / "diagrams"
    mmd_files = list(diagram_dir.glob("*.mmd")) if diagram_dir.exists() else []
    infographic_files = list(assets_dir.glob("*infographic*")) if assets_dir.exists() else []

    # One diagram is expected to cover architecture (see check_article_content).
    # A second visual asset is required once the article enumerates 3+
    # comparable concepts in bullet/numbered form, per aep/prompts/writer.md's
    # "Concept density" rule — that content should be an infographic, not
    # another prose list.
    if len(mmd_files) + len(infographic_files) < 2:
        return [
            f"article.md enumerates {concept_count} bold-labeled bullet/numbered "
            "items but ships only one diagram/infographic asset — render that "
            "content as a concept-infographic (aep/pipelines/generate_infographic.py) "
            "instead of leaving it as prose bullets"
        ]
    return []


def check_execution(article_dir: pathlib.Path) -> List[str]:
    """Actually run project/'s documented command — not just check it exists.

    This is what makes "never publish unexecuted code" (aep/README.md rule 1)
    a mechanical fact rather than a prompt request. It also cross-checks that
    article.md isn't left with a stale "not executed" disclaimer once the
    code is verified to run.
    """
    project_dir = article_dir / "project"
    readme_path = project_dir / "README.md"
    if not readme_path.exists():
        return []  # already reported by check_project_folder

    readme_text = readme_path.read_text(encoding="utf-8")
    match = re.search(r"##\s*Run it\s*\n```(?:bash|sh)?\n(.+?)```", readme_text, flags=re.S | re.I)
    if not match:
        return [
            f"{readme_path.relative_to(REPO_ROOT)} has no '## Run it' section with a "
            "fenced ```bash block — CI needs a literal command to execute"
        ]

    command_lines = [
        line.strip() for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
        # We already run with cwd=project_dir, so a leading `cd <dir>` in the
        # documented block (written for a human copy-pasting from repo root)
        # is a no-op here, not the actual command to execute.
        and not re.match(r"^cd\s+", line.strip())
    ]
    if not command_lines:
        return [f"{readme_path.relative_to(REPO_ROOT)}'s 'Run it' block has no executable command"]

    command = command_lines[0]
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return [f"could not parse run command '{command}': {e}"]

    try:
        result = subprocess.run(
            parts, cwd=project_dir, capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return [f"run command '{command}' references a program not found on PATH"]
    except subprocess.TimeoutExpired:
        return [
            f"run command '{command}' did not finish within 30s — if it genuinely "
            "needs network access or a live external endpoint (e.g. a real cloud "
            "API), say so explicitly in article.md instead of shipping a command "
            "CI can't complete"
        ]

    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip()[-800:]
        return [f"project code failed to execute (`{command}`, exit {result.returncode}):\n{tail}"]

    article_path = article_dir / "article.md"
    if article_path.exists():
        article_lower = article_path.read_text(encoding="utf-8").lower()
        stale = next((p for p in STALE_EXECUTION_PHRASES if p in article_lower), None)
        if stale:
            return [
                f"project code executed successfully in CI (`{command}`), but article.md "
                f"still contains {stale!r} — update the execution-status note so it "
                "doesn't undersell verified-working code"
            ]

    return []


def check_build_evidence(article_dir: pathlib.Path) -> List[str]:
    """Mechanically enforce 'never publish unexecuted code' (aep/README.md rule 1).

    A project/ folder full of source files proves nothing was fabricated as
    text, but it doesn't prove the code actually runs. build-artifact.json
    (aep/schemas/build-artifact.schema.json) is where that gets recorded --
    require it to exist and say the build genuinely passed, not just that
    someone traced it by eye.

    Complementary to check_execution above, not redundant: this verifies the
    agent recorded honest evidence (aep/prompts/production-engineering.md);
    check_execution independently re-runs the code right now in CI, which
    catches evidence that's gone stale (recorded once, then the code quietly
    broke in a later commit).
    """
    build_path = article_dir / "project" / "build-artifact.json"
    if not build_path.exists():
        return [
            f"missing {build_path.relative_to(REPO_ROOT)} -- the mini-project must be "
            "actually run and its result recorded, not just traced by eye"
        ]

    try:
        build = json.loads(build_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{build_path.relative_to(REPO_ROOT)} is not valid JSON: {exc}"]

    required = ["artifact_id", "topic", "build_status", "executed_checks", "generated_at"]
    missing = [f for f in required if f not in build]
    if missing:
        return [f"{build_path.relative_to(REPO_ROOT)} missing required fields: {missing}"]

    if build["build_status"] != "passed":
        return [
            f"{build_path.relative_to(REPO_ROOT)} records build_status="
            f"'{build['build_status']}' -- the mini-project must actually run "
            "successfully (see aep/prompts/production-engineering.md) before this "
            "counts as publish-ready, per aep/README.md's 'never publish "
            "unexecuted code' rule"
        ]

    if not build["executed_checks"]:
        return [f"{build_path.relative_to(REPO_ROOT)} has build_status=passed but no executed_checks recorded"]
    return []


def validate_article(article_dir: pathlib.Path) -> List[str]:
    errors: List[str] = []
    if not article_dir.exists():
        return [f"article directory does not exist: {article_dir}"]
    errors += check_publish_draft(article_dir)
    errors += check_article_content(article_dir)
    errors += check_hero_image(article_dir)
    errors += check_project_folder(article_dir)
    errors += check_topic_research_decision(article_dir)
    errors += check_research_bundle(article_dir)
    errors += check_style(article_dir)
    errors += check_infographic(article_dir)
    errors += check_execution(article_dir)
    errors += check_build_evidence(article_dir)
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
