#!/usr/bin/env python3
import argparse
import json
import pathlib
from typing import Any, Dict, List


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_run_dir(mode: str) -> pathlib.Path:
    mode_dir = REPO_ROOT / "aep" / "out" / mode
    pointer = load_json(mode_dir / "last-run.json")
    return REPO_ROOT / "aep" / "out" / mode / pointer["latest_run_id"]


def assert_required(obj: Dict[str, Any], required: List[str], name: str) -> None:
    missing = [field for field in required if field not in obj]
    if missing:
        raise ValueError(f"{name} missing required fields: {missing}")


def validate_ranked_topics(payload: Dict[str, Any]) -> None:
    assert_required(payload, ["ranked_topics"], "ranked-topics")
    ranked_topics = payload["ranked_topics"]
    if not isinstance(ranked_topics, list) or not ranked_topics:
        raise ValueError("ranked-topics.ranked_topics must be a non-empty array")
    for item in ranked_topics:
        assert_required(item, ["topic", "scores", "overall_score", "ranked_at"], "ranked-topic-item")
        scores = item["scores"]
        assert_required(scores, ["evergreen", "practical", "knowledge_gap", "virality"], "ranked-topic-scores")
        for score_name, value in scores.items():
            if not isinstance(value, (int, float)) or value < 0 or value > 100:
                raise ValueError(f"invalid score {score_name}={value}")
        if item["overall_score"] < 0 or item["overall_score"] > 100:
            raise ValueError("overall_score out of range")


def validate_research_bundle(payload: Dict[str, Any]) -> None:
    assert_required(payload, ["topic", "objective", "official_references", "claims"], "research-bundle")
    if not payload["official_references"]:
        raise ValueError("research-bundle requires official references")
    for claim in payload["claims"]:
        assert_required(claim, ["statement", "reference_urls"], "research-claim")
        if not claim["reference_urls"]:
            raise ValueError("research claim requires reference URLs")


def validate_build(payload: Dict[str, Any]) -> None:
    assert_required(payload, ["artifact_id", "topic", "build_status", "executed_checks", "generated_at"], "build-artifact")
    if payload["build_status"] not in ("passed", "failed"):
        raise ValueError("invalid build status")
    if not payload["executed_checks"]:
        raise ValueError("executed_checks must be non-empty")
    for check in payload["executed_checks"]:
        assert_required(check, ["name", "status"], "build-check")
        if check["status"] not in ("passed", "failed"):
            raise ValueError("invalid check status")


def validate_audit(payload: Dict[str, Any], expected_type: str) -> None:
    assert_required(payload, ["audit_type", "score", "status", "findings", "audited_at"], f"{expected_type}-audit")
    if payload["audit_type"] != expected_type:
        raise ValueError(f"audit_type must be {expected_type}")
    if payload["status"] not in ("passed", "failed"):
        raise ValueError("invalid audit status")
    if payload["score"] < 0 or payload["score"] > 100:
        raise ValueError("audit score out of range")
    for finding in payload["findings"]:
        assert_required(finding, ["severity", "summary"], "audit-finding")


def validate_publish(payload: Dict[str, Any]) -> None:
    assert_required(payload, ["external_id", "title", "status", "body_path", "references", "human_approval_required"], "publish-draft")
    if payload["status"] not in ("Draft - Pending Human Approval", "Ready to Publish"):
        raise ValueError("invalid publish status")
    if payload["human_approval_required"] is not True:
        raise ValueError("human approval must be true")
    if not payload["references"]:
        raise ValueError("publish draft must include references")


def validate_summary(payload: Dict[str, Any]) -> None:
    assert_required(payload, ["run_id", "mode", "run_timestamp_utc", "pipeline_status", "artifacts"], "run-summary")
    if payload["pipeline_status"] not in ("passed", "failed"):
        raise ValueError("invalid pipeline status")


def validate_mode(mode: str) -> None:
    run_dir = latest_run_dir(mode)
    files = {
        "topic-signals.json": run_dir / "topic-signals.json",
        "ranked-topics.json": run_dir / "ranked-topics.json",
        "research-bundle.json": run_dir / "research-bundle.json",
        "build-artifact.json": run_dir / "build-artifact.json",
        "technical-audit.json": run_dir / "technical-audit.json",
        "platform-audit.json": run_dir / "platform-audit.json",
        "publish-draft.json": run_dir / "publish-draft.json",
        "analytics.json": run_dir / "analytics.json",
        "run-summary.json": run_dir / "run-summary.json",
        "article_draft.md": run_dir / "article_draft.md",
        "architecture.mmd": run_dir / "architecture.mmd",
        "notion_draft.md": run_dir / "notion_draft.md",
    }
    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        raise ValueError(f"missing generated files: {missing}")

    validate_ranked_topics(load_json(files["ranked-topics.json"]))
    validate_research_bundle(load_json(files["research-bundle.json"]))
    validate_build(load_json(files["build-artifact.json"]))
    validate_audit(load_json(files["technical-audit.json"]), "technical")
    validate_audit(load_json(files["platform-audit.json"]), "platform")
    validate_publish(load_json(files["publish-draft.json"]))
    validate_summary(load_json(files["run-summary.json"]))

    print(f"validated mode={mode} run_dir={run_dir.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated AEP pipeline artifacts.")
    parser.add_argument("--mode", choices=["morning", "evening"], required=True)
    args = parser.parse_args()
    validate_mode(args.mode)


if __name__ == "__main__":
    main()
