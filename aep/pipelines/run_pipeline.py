#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
from typing import Dict, List, Optional, Tuple

import fetch_trend_signals
import generate_hero_image

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AEP_DIR = REPO_ROOT / "aep"
ARTICLES_DIR = REPO_ROOT / "articles"

# Below this, a candidate signal is close enough to something already
# published that it's excluded from ranking entirely (not just penalized).
DUPLICATE_EXCLUDE_THRESHOLD = 0.6
# Below this combined (similarity*0.6 + relevance*0.4) score, a series part's
# fixed title has no strong live supporting evidence this run — flagged, not
# fatal (the writer/research agent does the real research regardless).
TREND_SUPPORT_STRONG_THRESHOLD = 0.35

STOPWORDS = {
    "the", "a", "an", "of", "to", "for", "in", "on", "and", "or", "with",
    "is", "are", "how", "what", "why", "your", "this", "that", "new",
    "using", "part", "series", "into", "from", "about", "vs",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _keywords(text: str) -> set:
    words = re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def topic_similarity(a: str, b: str) -> float:
    """Deterministic Jaccard similarity over significant words — no embeddings,
    no LLM call, fully explainable. Good enough to catch "this is basically
    the same topic again," not meant to catch subtle paraphrases."""
    ka, kb = _keywords(a), _keywords(b)
    if not ka or not kb:
        return 0.0
    return round(len(ka & kb) / len(ka | kb), 3)


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
        # The plan is only ever written once, in whichever part first defined
        # it — later parts aren't guaranteed to carry their own copy (observed:
        # mcp-deep-dive/part-02 doesn't have one). Search newest-to-oldest
        # instead of assuming the latest part has it, or an existing series
        # silently gets treated as finished/absent.
        plan = None
        for part_dir in reversed(part_dirs):
            plan_path = part_dir / "series_plan.json"
            if plan_path.exists():
                try:
                    plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    break
                except json.JSONDecodeError:
                    continue
        if plan is None:
            continue
        total_parts = len(plan.get("series_titles", {})) or len(part_dirs)
        next_part = len(part_dirs) + 1
        if next_part <= total_parts:
            return series_dir.name, next_part, plan
    return None


def collect_published_topics(articles_dir: pathlib.Path) -> List[Tuple[str, str]]:
    """(topic_text, repo-relative-path) for every already-shipped research-bundle.json.

    This is what makes de-duplication self-updating: it's derived from repo
    state on every run, not a list someone has to remember to maintain.
    """
    results: List[Tuple[str, str]] = []
    if not articles_dir.exists():
        return results
    for bundle_path in sorted(articles_dir.glob("**/research-bundle.json")):
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        topic = bundle.get("topic")
        if topic:
            results.append((topic, str(bundle_path.relative_to(REPO_ROOT))))
    return results


def rank_topics(
    signals: List[dict], published_topics: List[Tuple[str, str]], run_ts: str
) -> Tuple[List[dict], List[dict]]:
    """Score + rank live signals; hard-exclude near-duplicates of already-published
    topics (kept visible in the `excluded` list for transparency, not silently dropped).

    Weights (sum to 100): freshness 25, relevance 30, practicality 20, novelty 15,
    official-source nudge 10 (5 if not an official/primary source). There is no
    "virality" term — this pipeline has no live engagement-metric source, and a
    fabricated placeholder number would be worse than not having one.
    """
    ranked: List[dict] = []
    excluded: List[dict] = []

    for item in signals:
        best_sim, best_match = 0.0, None
        for pub_topic, pub_path in published_topics:
            sim = topic_similarity(item["topic"], pub_topic)
            if sim > best_sim:
                best_sim, best_match = sim, (pub_topic, pub_path)

        hs = item["heuristic_scores"]
        freshness = round(hs["freshness"] * 100, 2)
        relevance = round(hs["relevance"] * 100, 2)
        practicality = round(hs["practicality"] * 100, 2)
        novelty = round((1.0 - best_sim) * 100, 2)
        overall = round(
            freshness * 0.25
            + relevance * 0.30
            + practicality * 0.20
            + novelty * 0.15
            + (10 if item.get("official_source") else 5),
            2,
        )

        entry = {
            "topic": item["topic"],
            "ranked_at": run_ts,
            "scores": {
                "freshness": freshness,
                "relevance": relevance,
                "practicality": practicality,
                "novelty": novelty,
            },
            "overall_score": overall,
            "references": [item["evidence_url"]],
            "similarity_to_existing": best_sim,
            "most_similar_existing": best_match[0] if best_match else None,
            "most_similar_existing_path": best_match[1] if best_match else None,
        }

        if best_sim >= DUPLICATE_EXCLUDE_THRESHOLD:
            entry["excluded_reason"] = (
                f"similarity={best_sim} to already-published topic "
                f"({best_match[1]}) meets the {DUPLICATE_EXCLUDE_THRESHOLD} exclusion threshold"
            )
            excluded.append(entry)
        else:
            ranked.append(entry)

    ranked.sort(key=lambda x: x["overall_score"], reverse=True)
    return ranked, excluded


def find_supporting_signals_for_title(signals: List[dict], fixed_title: str, top_n: int = 3) -> List[dict]:
    """For an already-committed series-part title, find the best live evidence
    for it — this does NOT re-pick the topic, only what backs it up."""
    scored = []
    for s in signals:
        sim = topic_similarity(fixed_title, s["topic"])
        combined = round(sim * 0.6 + s["heuristic_scores"]["relevance"] * 0.4, 3)
        scored.append((combined, sim, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"signal": s, "similarity": sim, "combined_score": combined} for combined, sim, s in scored[:top_n]]


def resolve_topic(
    articles_dir: pathlib.Path, signals: List[dict], ranked: List[dict]
) -> Tuple[Optional[str], pathlib.Path, dict]:
    """The core fix: series continuation and standalone topic-picking are two
    different decisions, not one. A series part's title is fixed once in
    series_plan.json when the series starts — trend data only ever supplies
    supporting evidence for it, never overrides it. Only when there's no
    active series does live-ranked ('what's the best new thing to write
    about') selection apply.
    """
    active = find_active_series(articles_dir)

    if active:
        series_name, next_part, plan = active
        target = articles_dir / series_name / f"part-{next_part:02d}"
        fixed_title = plan.get("series_titles", {}).get(str(next_part), "")
        supporting = find_supporting_signals_for_title(signals, fixed_title) if fixed_title else []
        strength = "strong" if supporting and supporting[0]["combined_score"] >= TREND_SUPPORT_STRONG_THRESHOLD else "weak"
        meta = {
            "kind": "series-continuation",
            "series_name": series_name,
            "series_part": next_part,
            "series_title": fixed_title,
            "trend_support_strength": strength,
            "supporting_signals": supporting,
        }
        return (fixed_title or None), target, meta

    if not ranked:
        return None, articles_dir / "untitled-article", {
            "kind": "standalone", "series_name": None, "series_part": None,
            "series_title": None, "trend_support_strength": None, "supporting_signals": [],
        }

    topic = ranked[0]["topic"]
    slug = slugify(topic)[:60] or "untitled-article"
    target = articles_dir / slug
    # ranked entries (from rank_topics) don't carry the original summary/
    # official_source fields — look the raw signal back up by topic so
    # build_research_bundle gets the same {"signal": <raw dict>, ...} shape
    # it expects from the series-continuation path. (Caught by testing this
    # path directly: without this, standalone runs silently produced zero
    # references/claims, which fails validate_artifacts.py's reference check.)
    signals_by_topic = {s["topic"]: s for s in signals}
    supporting = [
        {
            "signal": signals_by_topic.get(r["topic"]),
            "similarity": r["similarity_to_existing"],
            "combined_score": round(r["overall_score"] / 100, 3),
        }
        for r in ranked[:3]
    ]
    meta = {
        "kind": "standalone",
        "series_name": None,
        "series_part": None,
        "series_title": None,
        "trend_support_strength": "strong",
        "supporting_signals": supporting,
    }
    return topic, target, meta


def build_research_bundle(topic: str, target_meta: dict) -> dict:
    """Built from live, attributed signal data only — no hand-authored 'key facts'
    fabricated for a topic the deterministic pipeline can't actually verify.
    Deep factual research remains the research/writer agent's job
    (aep/prompts/research.md, aep/prompts/writer.md) — this is a sourced
    starting point, not a finished bundle."""
    supporting = target_meta.get("supporting_signals", [])
    official_domains = fetch_trend_signals.load_config().get("official_domains", [])

    all_refs, official_refs, claims = [], [], []
    for entry in supporting:
        sig = entry.get("signal")
        if not sig:
            continue
        url = sig["evidence_url"]
        all_refs.append(url)
        if sig.get("official_source") or fetch_trend_signals.is_official(url, official_domains):
            official_refs.append(url)
        statement = sig.get("summary") or sig["topic"]
        claims.append({"statement": f"{statement} (source: {sig['topic']})", "reference_urls": [url]})

    if not official_refs and all_refs:
        official_refs = all_refs[:1]
    supporting_refs = [u for u in all_refs if u not in official_refs]

    if target_meta["kind"] == "series-continuation":
        objective = (
            f"Part {target_meta['series_part']} of the {target_meta['series_name']} series: {topic}. "
            f"Live trend support this run: {target_meta['trend_support_strength']} "
            "(see supporting_signals for what backs it) — deep research is still the "
            "writer/research agent's job, this is a sourced starting point only."
        )
    else:
        objective = (
            f"Standalone article on: {topic}. Selected as the top live-ranked, "
            "non-duplicate candidate this run — see ranked-topics.json for the full pool "
            "and why alternatives scored lower."
        )

    return {
        "topic": topic,
        "objective": objective,
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
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("\n".join(output).strip() + "\n", encoding="utf-8")
    return proc.returncode == 0, str(evidence_path.relative_to(REPO_ROOT))


def write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_phase_artifacts(
    mode: str,
    run_ts: str,
    out_dir: pathlib.Path,
    topic: Optional[str],
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

    # Replaces the old check that tested for one specific historical file's
    # existence forever — meaningless once the pipeline stopped being
    # hardcoded to a single seed topic. This checks the thing that actually
    # matters now: did topic resolution succeed this run.
    pass_topic = bool(topic)
    topic_evidence_path = evidence_dir / "check-topic-resolved.log"
    write_text(topic_evidence_path, f"resolved_topic={topic!r}\nresolved={str(pass_topic).lower()}\n")
    checks.append(
        {
            "name": "topic-resolved",
            "status": "passed" if pass_topic else "failed",
            "evidence_path": str(topic_evidence_path.relative_to(REPO_ROOT)),
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
        "artifact_id": f"{mode}-{slugify(topic) if topic else 'no-topic-resolved'}",
        "topic": topic or "No topic resolved this run",
        "build_status": build_status,
        "executed_checks": checks,
        "generated_at": run_ts,
        "repo_ref": "local-working-copy",
    }

    article_output = out_dir / "article_draft.md"
    article_lines = [
        f"# {research_bundle['topic']}",
        "",
        "**Status:** Draft - Pending Human Approval",
        "",
        "## Problem Statement",
        research_bundle["objective"],
        "",
        "## Why Now (Trend Signals)",
        "\n".join(f"- {item['topic']} (score: {item['overall_score']})" for item in ranked_topics[:3])
        or "(no live signals scored this run — see fetch_errors)",
        "",
        "## Build Walkthrough (Teach by Building)",
        "1. Fetch live trend signals from configured RSS/Atom feeds (fetch_trend_signals.py).",
        "2. De-duplicate against already-published articles/** topics.",
        "3. Resolve topic: fixed series-part title if a series is active, else top-ranked live candidate.",
        "4. Build research bundle with attributed references and traceable claims.",
        "5. Produce evidence-backed build checks before draft packaging.",
        "",
        "## References (Official Preferred)",
        "\n".join(f"- {url}" for url in research_bundle["official_references"] + research_bundle.get("supporting_references", []))
        or "(none captured this run)",
    ]
    write_text(article_output, "\n".join(article_lines) + "\n")

    diagram_output = out_dir / "architecture.mmd"
    write_text(
        diagram_output,
        "graph TD\n"
        "  A[Live RSS/Atom Feeds] --> B[Fetch + Score Signals]\n"
        "  B --> C[De-duplicate vs articles/**]\n"
        "  C --> D[Resolve Topic: series-fixed or top-ranked]\n"
        "  D --> E[Research Bundle]\n"
        "  E --> F[Build + Evidence]\n"
        "  F --> G[Audits]\n"
        "  G --> H[Publish Draft Package]\n",
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
            "problem_statement": f"Explain and demonstrate: {topic}.",
            "trend_summary": f"Trend support strength this run: {target_meta.get('trend_support_strength') or 'n/a'}.",
            "architecture_summary": "Pipeline stages are deterministic and auditable across fetch, dedup, resolve, research, build, audit, and packaging.",
            "build_steps": "Live signal fetch -> dedup vs published -> topic resolution -> research bundle -> build evidence -> audits -> draft packaging.",
            "diagram_links": f"- {str((out_dir / 'architecture.mmd').relative_to(REPO_ROOT))}",
            "project_path": publish_draft["project_path"],
            "execution_evidence": f"- Build status: {technical_audit['status']}\n- Platform status: {platform_audit['status']}",
            "tradeoffs": "Deterministic topic discovery/ranking is reliable and testable, but the deep factual research and writing remain agent tasks, not automated.",
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

    config = fetch_trend_signals.load_config()
    signals, fetch_errors = fetch_trend_signals.fetch_all(config, run_ts)
    published_topics = collect_published_topics(ARTICLES_DIR)
    ranked_topics, excluded_duplicates = rank_topics(signals, published_topics, run_ts)

    topic, target_dir, target_meta = resolve_topic(ARTICLES_DIR, signals, ranked_topics)
    research_bundle = build_research_bundle(topic or "No topic resolved", target_meta)

    build_artifact, article_output, diagram_output = build_phase_artifacts(
        mode, run_ts, out_dir, topic, research_bundle, ranked_topics
    )
    technical_audit, platform_audit = build_audits(build_artifact, research_bundle, article_output, run_ts)

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

    write_json(out_dir / "topic-signals.json", {"signals": signals, "fetch_errors": fetch_errors})
    write_json(out_dir / "ranked-topics.json", {"ranked_topics": ranked_topics, "excluded_duplicates": excluded_duplicates})
    write_json(out_dir / "research-bundle.json", research_bundle)
    write_json(out_dir / "build-artifact.json", build_artifact)
    write_json(out_dir / "technical-audit.json", technical_audit)
    write_json(out_dir / "platform-audit.json", platform_audit)
    write_json(out_dir / "publish-draft.json", publish_draft)
    write_json(out_dir / "analytics.json", analytics)

    topic_discovery = {
        "run_id": run_id,
        "signals_fetched": len(signals),
        "fetch_errors": fetch_errors,
        "published_topics_considered": [t for t, _ in published_topics],
        "excluded_duplicates": excluded_duplicates,
        "resolution": {
            "kind": target_meta["kind"],
            "topic": topic,
            "target_dir": str(target_dir.relative_to(REPO_ROOT)),
            "series_name": target_meta["series_name"],
            "series_part": target_meta["series_part"],
            "trend_support_strength": target_meta.get("trend_support_strength"),
            "reasoning": (
                "Series-continuation: topic is the fixed title from series_plan.json, "
                "never re-picked from trend data. Supporting signals only back it up."
                if target_meta["kind"] == "series-continuation"
                else "Standalone: topic is the top-ranked, non-duplicate live signal this run."
            ),
        },
    }
    write_json(out_dir / "topic-discovery.json", topic_discovery)

    pipeline_status = "passed" if (
        bool(topic)
        and build_artifact["build_status"] == "passed"
        and technical_audit["status"] == "passed"
        and platform_audit["status"] == "passed"
    ) else "failed"

    write_json(
        out_dir / "run-summary.json",
        {
            "run_id": run_id,
            "mode": mode,
            "run_timestamp_utc": run_ts,
            "pipeline_status": pipeline_status,
            "topic_resolved": bool(topic),
            "artifacts": {
                "topic_signals": str((out_dir / "topic-signals.json").relative_to(REPO_ROOT)),
                "ranked_topics": str((out_dir / "ranked-topics.json").relative_to(REPO_ROOT)),
                "topic_discovery": str((out_dir / "topic-discovery.json").relative_to(REPO_ROOT)),
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
