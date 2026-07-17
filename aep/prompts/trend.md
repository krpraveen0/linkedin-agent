# Trend Agent Prompt Template

Role: This step is now handled deterministically — `aep/pipelines/fetch_trend_signals.py`
fetches live RSS/Atom feeds (config: `aep/pipelines/trend_sources.json`) and scores
each item with plain heuristics (freshness from `pubDate`, relevance from keyword
overlap, practicality from how-to language). No LLM call, no API key, fully
reproducible — see the module docstring for exactly how each score is computed.

## Where this agent role still applies

The deterministic fetcher only knows about the feeds listed in
`trend_sources.json`. If you're doing research and find a genuinely
high-signal topic from a source that isn't in that list (a conference talk,
a GitHub release, a paper), you can still surface it manually:

- Add real candidate data to a `TopicSignal`-shaped entry (see
  `aep/schemas/topic-signal.schema.json`) — don't invent scores; if you can't
  point to a real publish date and a real excerpt, it doesn't belong in the pool.
- Prefer expanding `trend_sources.json`'s `feeds` list over one-off manual
  entries when the source is likely to matter again (i.e. it's a blog with an
  RSS feed) — that way every future run benefits, not just this one.

## The one rule that doesn't change

**Series parts never get their topic from trend ranking.** If
`aep/pipelines/run_pipeline.py` reports `"kind": "series-continuation"` in
`topic-discovery.json`, the topic is fixed by that series's own
`series_plan.json` — trend signals only supply supporting evidence/timeliness
for that already-committed title, never a replacement for it. Live-ranked
topic selection only applies when there's no active series (see
`aep/prompts/writer.md`'s "Where to write it" section and
`run_pipeline.py`'s `resolve_topic()`).

## De-duplication

`run_pipeline.py` excludes any live signal too similar (Jaccard similarity
≥ 0.6) to an already-published `articles/**/research-bundle.json` topic —
check `ranked-topics.json`'s `excluded_duplicates` and `topic-discovery.json`
before treating a topic as genuinely new.
