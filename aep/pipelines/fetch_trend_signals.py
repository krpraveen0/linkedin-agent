#!/usr/bin/env python3
"""Deterministically fetch and score live trend signals — no LLM, no API key.

Replaces the old static, hardcoded articles/mcp-deep-dive/part-01/trend_signals.json
seed file that every pipeline run used to re-read forever. This module fetches
real RSS/Atom feeds (config in trend_sources.json) via stdlib urllib/xml.etree
only, and scores each item with plain, explainable heuristics — no external
LLM API call, per aep/policies/no-external-llm-policy.md. A feed that's
unreachable is skipped with a recorded error; it never crashes the run.

Scoring is intentionally simple and inspectable:
  - freshness:    decays linearly from 1.0 (published today) to 0.0 (21+ days old)
  - relevance:    fraction of configured focus_keywords found in title+summary
  - practicality: 0.3 baseline, +0.7 if a how-to/build-style phrase is present
"""
import argparse
import datetime as dt
import email.utils
import json
import pathlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_PATH = pathlib.Path(__file__).resolve().parent / "trend_sources.json"
USER_AGENT = "Mozilla/5.0 (compatible; AEP-trend-fetcher/1.0; +https://github.com)"
FETCH_TIMEOUT = 12
FRESHNESS_HALF_LIFE_DAYS = 21
# Some feeds (observed: huggingface.co/blog/feed.xml) return their entire
# historical archive rather than just recent posts. Anything older than this
# is dropped before scoring — there's no value ranking a 3-year-old post
# against this week's release, and it keeps the candidate pool small enough
# to actually read.
MAX_ENTRY_AGE_DAYS = 30


def load_config(config_path: pathlib.Path = CONFIG_PATH) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


def _strip_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _local_find(elem: ET.Element, name: str) -> Optional[ET.Element]:
    for child in elem:
        if _strip_tag(child.tag) == name:
            return child
    return None


def _local_findall(elem: ET.Element, name: str) -> List[ET.Element]:
    return [child for child in elem if _strip_tag(child.tag) == name]


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None or elem.text is None:
        return ""
    return re.sub(r"<[^>]+>", " ", elem.text).strip()


def _parse_date(raw: str) -> Optional[dt.datetime]:
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except (TypeError, ValueError):
        pass
    try:
        iso = raw.strip().replace("Z", "+00:00")
        return dt.datetime.fromisoformat(iso)
    except ValueError:
        return None


def fetch_feed_bytes(url: str, timeout: int = FETCH_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_feed(xml_bytes: bytes, feed_url: str) -> List[dict]:
    """Parse RSS 2.0 <item> or Atom <entry> elements into plain dicts."""
    root = ET.fromstring(xml_bytes)
    items: List[ET.Element] = []
    # RSS: rss/channel/item. Atom: feed/entry.
    channel = _local_find(root, "channel")
    if channel is not None:
        items = _local_findall(channel, "item")
    if not items and _strip_tag(root.tag) == "feed":
        items = _local_findall(root, "entry")

    entries = []
    for item in items:
        title = _text(_local_find(item, "title"))
        link_elem = _local_find(item, "link")
        if link_elem is not None and link_elem.get("href"):
            link = link_elem.get("href")
        else:
            link = _text(link_elem)
        summary = _text(_local_find(item, "description")) or _text(_local_find(item, "summary"))
        published_raw = (
            _text(_local_find(item, "pubDate"))
            or _text(_local_find(item, "published"))
            or _text(_local_find(item, "updated"))
        )
        if not title or not link:
            continue
        entries.append(
            {
                "source": feed_url,
                "title": title,
                "link": link,
                "summary": summary[:300],
                "published": published_raw,
                "published_dt": _parse_date(published_raw),
            }
        )
    return entries


def score_freshness(published_dt: Optional[dt.datetime], now: dt.datetime) -> float:
    if published_dt is None:
        return 0.3  # unknown age — don't reward or fully penalize
    age_days = max(0.0, (now - published_dt).total_seconds() / 86400)
    score = 1.0 - (age_days / FRESHNESS_HALF_LIFE_DAYS)
    return round(max(0.0, min(1.0, score)), 3)


def score_relevance(title: str, summary: str, focus_keywords: List[str]) -> float:
    haystack = f"{title} {summary}".lower()
    hits = sum(1 for kw in focus_keywords if kw.lower() in haystack)
    # 6+ distinct keyword hits maxes out relevance; avoids one giant list making
    # everything score 1.0 while still rewarding genuinely on-topic pieces.
    return round(min(1.0, hits / 6), 3)


def score_practicality(title: str, summary: str, practicality_keywords: List[str]) -> float:
    haystack = f"{title} {summary}".lower()
    hit = any(kw.lower() in haystack for kw in practicality_keywords)
    return round(0.3 + (0.7 if hit else 0.0), 3)


def is_official(url: str, official_domains: List[str]) -> bool:
    return any(domain in url for domain in official_domains)


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


def fetch_all(config: dict, run_ts: str, now: Optional[dt.datetime] = None) -> Tuple[List[dict], List[dict]]:
    """Returns (signals, fetch_errors). A feed failure never raises — it's recorded
    in fetch_errors and the rest of the feeds still get a chance to contribute."""
    now = now or dt.datetime.now(dt.timezone.utc)
    focus_keywords = config.get("focus_keywords", [])
    practicality_keywords = config.get("practicality_keywords", [])
    official_domains = config.get("official_domains", [])

    signals: List[dict] = []
    errors: List[dict] = []
    signal_idx = 1

    for feed_url in config.get("feeds", []):
        try:
            raw = fetch_feed_bytes(feed_url)
            entries = parse_feed(raw, feed_url)
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError, TimeoutError) as e:
            errors.append({"feed": feed_url, "error": f"{type(e).__name__}: {e}"})
            continue

        for entry in entries:
            published_dt = entry["published_dt"]
            if published_dt is not None:
                age_days = (now - published_dt).total_seconds() / 86400
                if age_days > MAX_ENTRY_AGE_DAYS:
                    continue

            freshness = score_freshness(published_dt, now)
            relevance = score_relevance(entry["title"], entry["summary"], focus_keywords)
            practicality = score_practicality(entry["title"], entry["summary"], practicality_keywords)
            signals.append(
                {
                    "id": f"sig-{signal_idx:03d}",
                    "captured_at": run_ts,
                    "source": entry["source"],
                    "topic": entry["title"],
                    "signal_type": classify_signal(entry["title"]),
                    "summary": entry["summary"],
                    "evidence_url": entry["link"],
                    "official_source": is_official(entry["link"], official_domains),
                    "published": entry["published"],
                    "heuristic_scores": {
                        "freshness": freshness,
                        "relevance": relevance,
                        "practicality": practicality,
                    },
                }
            )
            signal_idx += 1

    return signals, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and score live trend signals from configured RSS/Atom feeds.")
    parser.add_argument("--out", type=pathlib.Path, help="Write signals JSON here (defaults to stdout).")
    parser.add_argument("--config", type=pathlib.Path, default=CONFIG_PATH)
    args = parser.parse_args()

    config = load_config(args.config)
    run_ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    signals, errors = fetch_all(config, run_ts)

    payload = {"signals": signals, "fetch_errors": errors, "fetched_at": run_ts}
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {len(signals)} signals ({len(errors)} feed errors) to {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
