#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
from typing import Dict, List, Optional, Tuple

import generate_hero_image

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SERIES_DIR = REPO_ROOT / "articles" / "mcp-deep-dive" / "part-01"
AEP_DIR = REPO_ROOT / "aep"
ARTICLES_DIR = REPO_ROOT / "articles"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def find_active_series(articles_dir: pathlib.Path) -> Optional[Tuple[str, int, dict]]:
    """First series under articles/ with parts remaining per its own series_plan.json, else None.

    Best-effort only: the agent that actually writes the article has full repo
    context and should override this if a better continuation/new-series call applies.
    """
    if not articles_dir.exists():
        return None
    for series_dir in sorted(p for p in articles_dir.iterdir() if p.is_dir()):
        part_dirs = sorted(p for p in series_dir.glob("part-*") if p.is_dir())
        if not part_dirs:
            continue
        plan_path = part_dirs[-1] / "series_plan.json"
        if not plan_path.exists():
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        total_parts = len(plan.get("series_titles", {})) or len(part_dirs)
        next_part = len(part_dirs) + 1
        if next_part <= total_parts:
            return series_dir.name, next_part, plan
    return None


def resolve_target_article_dir(topic: str, articles_dir: pathlib.Path) -> Tuple[pathlib.Path, dict]:
    """Propose (not create) the publish-ready folder this article belongs in."""
    active = find_active_series(articles_dir)
    if active:
        series_name, next_part, plan = active
        target = articles_dir / series_name / f"part-{next_part:02d}"
        return target, {
            "kind": "series-continuation",
            "series_name": series_name,
            "series_part": next_part,
            "series_title": plan.get("series_titles", {}).get(str(next_part), ""),
        }
    slug = slugify(topic)[:60] or "untitled-article"
    target = articles_dir / slug
    return target, {"kind": "standalone", "series_name": None, "series_part": None, "series_title": None}


def load_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def classify_signal(title: str) -> str:
    lowered = title.lower()
    if "benchmark" in lowered:
        return "benchmark"
    if "incident" in lowered:
        return "incident"
    if "release" in lowered or "introducing" in lowered or "welcome" in lowered:
        return "release"
    if "discussion" in lowered or "debate" in lowered:
        return "discussion"
    return "trend"


def is_official(url: str) -> bool:
    return any(
        domain in url
        for domain in [
            "anthropic.com",
            "modelcontextprotocol.io",
            "github.com/modelcontextprotocol",
            "microsoft.com",
            "aws.amazon.com",
            "blog.google",
        ]
    )


def normalize_topic_signals(raw_signals: List[dict], run_ts: str) -> List[dict]:
    signals = []
    for idx, item in enumerate(raw_signals, start=1):
        evidence_url = item["link"]
        signals.append(
            {
                "id": f"sig-{idx:03d}",
                "captured_at": run_ts,
                "source": item["source"],
                "topic": item["title"],
                "signal_type": classify_signal(item["title"]),
                "summary": item.get("summary", "")[:300],
                "evidence_url": evidence_url,
                "official_source": is_official(evidence_url),
            }
        )
    return signals


def rank_topics(raw_signals: List[dict], run_ts: str) -> List[dict]:
    ranked = []
    for item in raw_signals:
        practicality = round(float(item.get("llm_practicality", 0.0)) * 100, 2)
        freshness = round(float(item.get("llm_freshness", 0.0)) * 100, 2)
        relevance = round(float(item.get("llm_relevance", 0.0)) * 100, 2)
        evergreen = round((freshness * 0.4) + (relevance * 0.6), 2)
        knowledge_gap = round((100 - relevance) * 0.35 + relevance * 0.65, 2)
        virality = round(float(item.get("heuristic_score", 0.0)) * 100, 2)
        overall = round(evergreen * 0.35 + practicality * 0.35 + knowledge_gap * 0.2 + virality * 0.1, 2)
        ranked.append(
            {
                "topic": item["title"],
                "ranked_at": run_ts,
                "scores": {
                    "evergreen": evergreen,
                    "practical": practicality,
                    "knowledge_gap": knowledge_gap,
                    "virality": virality,
                },
                "overall_score": overall,
                "references": [item["link"]],
            }
        )
    return sorted(ranked, key=lambda x: x["overall_score"], reverse=True)


def build_research_bundle(research_source: dict, ranked_topics: List[dict]) -> dict:
    topic = ranked_topics[0]["topic"] if ranked_topics else research_source["topic"]
    all_refs = research_source.get("source_links", [])
    official_refs = [url for url in all_refs if is_official(url)]
    if not official_refs and all_refs:
        official_refs = [all_refs[0]]
    supporting_refs = [url for url in all_refs if url not in official_refs]
    claims = []
    for fact in research_source.get("key_facts", []):
        refs = official_refs[:2] if official_refs else all_refs[:1]
        claims.append({"statement": fact, "reference_urls": refs})
    return {
        "topic": topic,
        "objective": research_source.get("part_theme", "Build a practical and reference-backed article draft."),
        "official_references": official_refs,
        "supporting_references": supporting_refs,
        "claims": claims,
    }


def run_check(command: List[str], cwd: pathlib.Path, evidence_path: pathlib.Path) -> Tuple[bool, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    output = []
    output.append(f"$ {' '.join(command)}")
    if proc.stdout:
        output.append("\n[stdout]\n" + proc.stdout.strip())
    if proc.stderr:
        output.append("\n[stderr]\n" + proc.stderr.strip())
    output.append(f"\nexit_code={proc.returncode}")
    write_text(evidence_path, "\n".join(output).strip() + "\n")
    return proc.returncode == 0, str(evidence_path.relative_to(REPO_ROOT))


def build_phase_artifacts(
    mode: str,
    run_ts: str,
    out_dir: pathlib.Path,
    research_bundle: dict,
    ranked_topics: List[dict],
) -> Tuple[dict, pathlib.Path, pathlib.Path]:
    evidence_dir = out_dir / "evidence"
    checks = []

    pass_json, json_evidence = run_check(
        ["python3", "-c", "import json,glob; [json.load(open(p)) for p in glob.glob('articles/**/*.json', recursive=True)]"],
        REPO_ROOT,
        evidence_dir / "check-json-articles.log",
    )
    checks.append({"name": "parse-article-json", "status": "passed" if pass_json else "failed", "evidence_path": json_evidence})

    pass_article = (SERIES_DIR / "article_draft.md").exists()
    article_evidence_path = evidence_dir / "check-article-draft.log"
    write_text(
        article_evidence_path,
        f"article_draft_path={SERIES_DIR / 'article_draft.md'}\nexists={str(pass_article).lower()}\n",
    )
    checks.append(
        {
            "name": "article-draft-exists",
            "status": "passed" if pass_article else "failed",
            "evidence_path": str(article_evidence_path.relative_to(REPO_ROOT)),
        }
    )

    has_official_refs = len(research_bundle["official_references"]) > 0
    refs_evidence_path = evidence_dir / "check-official-references.log"
    write_text(
        refs_evidence_path,
        "official_references_count="
        + str(len(research_bundle["official_references"]))
        + "\n"
        + "\n".join(research_bundle["official_references"])
        + "\n",
    )
    checks.append(
        {
            "name": "official-references-present",
            "status": "passed" if has_official_refs else "failed",
            "evidence_path": str(refs_evidence_path.relative_to(REPO_ROOT)),
        }
    )

    build_status = "passed" if all(c["status"] == "passed" for c in checks) else "failed"
    build_artifact = {
        "artifact_id": f"{mode}-{slugify(ranked_topics[0]['topic']) if ranked_topics else 'topic'}",
        "topic": ranked_topics[0]["topic"] if ranked_topics else "Unknown topic",
        "build_status": build_status,
        "executed_checks": checks,
        "generated_at": run_ts,
        "repo_ref": "local-working-copy",
    }

    article_output = out_dir / "article_draft.md"
    article_lines = [
        f"# {research_bundle['topic']}",
        "",
        f"**Status:** Draft - Pending Human Approval",
        "",
        "## Problem Statement",
        research_bundle["objective"],
        "",
        "## Why Now (Trend Signals)",
        "\n".join(f"- {item['topic']} (score: {item['overall_score']})" for item in ranked_topics[:3]),
        "",
        "## Build Walkthrough (Teach by Building)",
        "1. Collect deterministic trend signals from repository datasets.",
        "2. Rank topics using weighted scoring.",
        "3. Build research bundle with official references and traceable claims.",
        "4. Produce evidence-backed build checks before draft packaging.",
        "",
        "## References (Official Preferred)",
        "\n".join(f"- {url}" for url in research_bundle["official_references"] + research_bundle.get("supporting_references", [])),
    ]
    write_text(article_output, "\n".join(article_lines) + "\n")

    diagram_output = out_dir / "architecture.mmd"
    write_text(
        diagram_output,
        "graph TD\n"
        "  A[Trend Signals] --> B[Deterministic Ranking]\n"
        "  B --> C[Research Bundle]\n"
        "  C --> D[Build + Evidence]\n"
        "  D --> E[Audits]\n"
        "  E --> F[Publish Draft Package]\n"
        "  F --> G[Analytics Loop]\n",
    )
    return build_artifact, article_output, diagram_output


def make_audit(audit_type: str, run_ts: str, findings: List[dict], score: float) -> dict:
    status = "passed" if score >= 75 else "failed"
    return {
        "audit_type": audit_type,
        "score": round(score, 2),
        "status": status,
        "audited_at": run_ts,
        "findings": findings,
    }


def build_audits(build_artifact: dict, research_bundle: dict, article_output: pathlib.Path, run_ts: str) -> Tuple[dict, dict]:
    technical_score = 100.0
    tech_findings = []
    if build_artifact["build_status"] != "passed":
        technical_score -= 35
        tech_findings.append(
            {
                "severity": "high",
                "summary": "Build evidence checks did not fully pass.",
                "remediation": "Review failed checks and rerun pipeline.",
            }
        )
    if len(research_bundle["official_references"]) < 2:
        technical_score -= 15
        tech_findings.append(
            {
                "severity": "medium",
                "summary": "Low number of official references.",
                "remediation": "Expand official references for stronger support.",
            }
        )
    if not tech_findings:
        tech_findings.append({"severity": "low", "summary": "Technical evidence and references satisfy baseline checks."})

    platform_score = 100.0
    platform_findings = []
    article_text = article_output.read_text(encoding="utf-8")
    required_sections = ["Problem Statement", "Why Now (Trend Signals)", "Build Walkthrough", "References (Official Preferred)"]
    missing_sections = [section for section in required_sections if section not in article_text]
    if missing_sections:
        platform_score -= 30
        platform_findings.append(
            {
                "severity": "high",
                "summary": f"Missing required sections: {', '.join(missing_sections)}.",
                "remediation": "Ensure draft includes all required publication sections.",
            }
        )
    if len(article_text.split()) < 120:
        platform_score -= 15
        platform_findings.append(
            {
                "severity": "medium",
                "summary": "Draft is too short for publication readiness.",
                "remediation": "Add more explanatory detail and practical context.",
            }
        )
    if not platform_findings:
        platform_findings.append({"severity": "low", "summary": "Draft structure and readability checks passed."})

    return (
        make_audit("technical", run_ts, tech_findings, technical_score),
        make_audit("platform", run_ts, platform_findings, platform_score),
    )


def render_template(template_text: str, replacements: Dict[str, str]) -> str:
    rendered = template_text
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def build_publish_bundle(
    run_id: str,
    topic: str,
    article_path: pathlib.Path,
    references: List[str],
    technical_audit: dict,
    platform_audit: dict,
    out_dir: pathlib.Path,
    target_dir: pathlib.Path,
    target_meta: dict,
) -> Tuple[dict, pathlib.Path]:
    # Proposed final locations (not yet created here — the agent that writes the
    # real article is responsible for actually producing these files; see
    # aep/docs/agent-dispatch.md and aep/prompts/writer.md for the required layout).
    publish_draft = {
        "external_id": run_id,
        "title": f"{topic} — EngineeringCoders Draft",
        "status": "Draft - Pending Human Approval",
        "body_path": str(article_path.relative_to(REPO_ROOT)),
        "references": references if references else ["https://example.com/placeholder-reference"],
        "human_approval_required": True,
        "article_path": str((target_dir / "article.md").relative_to(REPO_ROOT)),
        "hero_image_path": str((target_dir / "assets" / "hero.png").relative_to(REPO_ROOT)),
        "diagram_paths": [str((target_dir / "assets" / "diagrams" / "architecture.mmd").relative_to(REPO_ROOT))],
        "project_path": str((target_dir / "project").relative_to(REPO_ROOT)),
        "series_name": target_meta["series_name"],
        "series_part": target_meta["series_part"],
    }
    template = (AEP_DIR / "publisher" / "notion-page-template.md").read_text(encoding="utf-8")
    notion_body = render_template(
        template,
        {
            "title": publish_draft["title"],
            "external_id": publish_draft["external_id"],
            "topic": topic,
            "series_name": target_meta["series_name"] or "(standalone article)",
            "hero_image_path": publish_draft["hero_image_path"],
            "problem_statement": "Explain practical MCP architecture choices for engineering teams.",
            "trend_summary": f"Top ranked topic score confirms current relevance for {topic}.",
            "architecture_summary": "Pipeline stages are deterministic and auditable across trend, research, build, audit, and packaging.",
            "build_steps": "Trend scoring -> research bundle -> build evidence -> audits -> draft packaging.",
            "diagram_links": f"- {str((out_dir / 'architecture.mmd').relative_to(REPO_ROOT))}",
            "project_path": publish_draft["project_path"],
            "execution_evidence": f"- Build status: {technical_audit['status']}\n- Platform status: {platform_audit['status']}",
            "tradeoffs": "Deterministic logic is reliable and testable, but less adaptive than model-generated content.",
            "references": "\n".join(f"- {url}" for url in publish_draft["references"]),
            "audit_scores": f"- Technical: {technical_audit['score']} ({technical_audit['status']})\n- Platform: {platform_audit['score']} ({platform_audit['status']})",
        },
    )
    notion_page_path = out_dir / "notion_draft.md"
    write_text(notion_page_path, notion_body)
    return publish_draft, notion_page_path


def build_analytics(run_ts: str, ranked_topics: List[dict], technical_audit: dict, platform_audit: dict) -> dict:
    top_score = ranked_topics[0]["overall_score"] if ranked_topics else 0
    audit_mean = round((technical_audit["score"] + platform_audit["score"]) / 2, 2)
    quality_gate = "pass" if technical_audit["status"] == "passed" and platform_audit["status"] == "passed" else "fail"
    recommendation = "Continue with current topic family and expand deeper implementation examples." if quality_gate == "pass" else "Revise research and draft structure before next cycle."
    return {
        "generated_at": run_ts,
        "top_topic": ranked_topics[0]["topic"] if ranked_topics else "Unknown",
        "top_topic_score": top_score,
        "technical_audit_score": technical_audit["score"],
        "platform_audit_score": platform_audit["score"],
        "audit_average_score": audit_mean,
        "quality_gate": quality_gate,
        "next_cycle_recommendation": recommendation,
    }


def run_pipeline(mode: str) -> pathlib.Path:
    run_ts = utc_now()
    run_id = f"{mode}-{run_ts.replace(':', '').replace('-', '')}"
    out_dir = AEP_DIR / "out" / mode / run_id
    latest_dir = AEP_DIR / "out" / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_signals = load_json(SERIES_DIR / "trend_signals.json")
    research_source = load_json(SERIES_DIR / "research.json")
    topic_signals = normalize_topic_signals(raw_signals, run_ts)
    ranked_topics = rank_topics(raw_signals, run_ts)
    research_bundle = build_research_bundle(research_source, ranked_topics)
    build_artifact, article_output, diagram_output = build_phase_artifacts(mode, run_ts, out_dir, research_bundle, ranked_topics)
    technical_audit, platform_audit = build_audits(build_artifact, research_bundle, article_output, run_ts)

    target_dir, target_meta = resolve_target_article_dir(research_bundle["topic"], ARTICLES_DIR)
    hero_preview_path = out_dir / "hero_preview.png"
    generate_hero_image.generate(
        title=research_bundle["topic"],
        kicker=target_meta["series_name"] or "engineering deep dive",
        out_path=hero_preview_path,
    )

    publish_draft, notion_draft = build_publish_bundle(
        run_id,
        research_bundle["topic"],
        article_output,
        research_bundle["official_references"] + research_bundle.get("supporting_references", []),
        technical_audit,
        platform_audit,
        out_dir,
        target_dir,
        target_meta,
    )
    analytics = build_analytics(run_ts, ranked_topics, technical_audit, platform_audit)

    write_json(out_dir / "topic-signals.json", {"signals": topic_signals})
    write_json(out_dir / "ranked-topics.json", {"ranked_topics": ranked_topics})
    write_json(out_dir / "research-bundle.json", research_bundle)
    write_json(out_dir / "build-artifact.json", build_artifact)
    write_json(out_dir / "technical-audit.json", technical_audit)
    write_json(out_dir / "platform-audit.json", platform_audit)
    write_json(out_dir / "publish-draft.json", publish_draft)
    write_json(out_dir / "analytics.json", analytics)
    write_json(
        out_dir / "run-summary.json",
        {
            "run_id": run_id,
            "mode": mode,
            "run_timestamp_utc": run_ts,
            "pipeline_status": "passed"
            if all(
                [
                    build_artifact["build_status"] == "passed",
                    technical_audit["status"] == "passed",
                    platform_audit["status"] == "passed",
                ]
            )
            else "failed",
            "artifacts": {
                "topic_signals": str((out_dir / "topic-signals.json").relative_to(REPO_ROOT)),
                "ranked_topics": str((out_dir / "ranked-topics.json").relative_to(REPO_ROOT)),
                "research_bundle": str((out_dir / "research-bundle.json").relative_to(REPO_ROOT)),
                "build_artifact": str((out_dir / "build-artifact.json").relative_to(REPO_ROOT)),
                "technical_audit": str((out_dir / "technical-audit.json").relative_to(REPO_ROOT)),
                "platform_audit": str((out_dir / "platform-audit.json").relative_to(REPO_ROOT)),
                "publish_draft": str((out_dir / "publish-draft.json").relative_to(REPO_ROOT)),
                "notion_draft": str(notion_draft.relative_to(REPO_ROOT)),
                "diagram_source": str(diagram_output.relative_to(REPO_ROOT)),
                "hero_image_preview": str(hero_preview_path.relative_to(REPO_ROOT)),
                "analytics": str((out_dir / "analytics.json").relative_to(REPO_ROOT)),
            },
            "target_article": {
                "kind": target_meta["kind"],
                "dir": str(target_dir.relative_to(REPO_ROOT)),
                "series_name": target_meta["series_name"],
                "series_part": target_meta["series_part"],
                "series_title": target_meta["series_title"],
                "note": "Proposed only — not created by this deterministic run. The agent "
                "writing the real article creates these files; see aep/prompts/writer.md.",
            },
        },
    )
    write_json(
        latest_dir / "last-run.json",
        {"latest_run_id": run_id, "run_timestamp_utc": run_ts, "summary_path": str((out_dir / "run-summary.json").relative_to(REPO_ROOT))},
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic AEP pipeline.")
    parser.add_argument("--mode", choices=["morning", "evening"], required=True)
    args = parser.parse_args()
    out_dir = run_pipeline(args.mode)
    print(f"AEP {args.mode} pipeline run completed: {out_dir.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
