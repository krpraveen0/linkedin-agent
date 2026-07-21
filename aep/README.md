# EngineeringCoders Autonomous Editorial Platform (AEP) — v1 Foundation

This module is an isolated foundation for a GitHub-native, Copilot-agent-first editorial platform.

## Isolation + non-invasive guarantees
- All AEP implementation is under `aep/`.
- Existing repository folders and automations are untouched.
- New workflows are uniquely named (`aep-*`) and scoped to `aep/**` where relevant.
- Current workflows outside AEP are not modified.

## Core operating constraints
- No external LLM API usage inside AEP.
- GitHub/Copilot agent-first architecture.
- Human approval is required before publication.
- Notion output is draft-first via MCP-friendly contracts.

## Constitution alignment
1. Never publish unexecuted code — mechanically enforced: CI (`aep-article-check.yml`
   → `validate_article.py`'s `check_execution`) actually runs `project/`'s
   documented command and fails the PR if it errors or if `article.md` still
   claims non-execution once the code is verified to run.
2. Prefer official documentation.
3. Every article teaches by building.
4. Every diagram is editable.
5. Every claim is referenced.
6. Quality over virality — mechanically backstopped: `check_style` flags a
   fixed list of AI-tell phrases, `check_infographic` requires a rendered
   visual (not prose bullets) once 3+ parallel concepts appear, and
   `aep/prompts/research.md`'s competitive-scan step requires a stated,
   verifiable differentiation from existing published content on the topic.
7. Human approval before publication.

## v1 scope in this folder
- `docs/`: concise implementation blueprint (`implementation-spec.md`) and
  the agent-dispatch guide (`agent-dispatch.md`).
- `schemas/`: contracts for AEP artifacts.
- `prompts/`: agent role templates — read by whichever agent (Copilot,
  Claude Code, opencode) is running the generative step; the contracts are
  the same regardless of which one you use.
- `pipelines/`: deterministic trend/research/audit pipeline
  (`run_pipeline.py`, `validate_artifacts.py`, `fetch_trend_signals.py`) plus
  the agent handoffs:
  - `github_api.py` — shared GitHub REST API glue (issues/comments/search);
    every other dispatch script imports this rather than duplicating it.
  - `dispatch_to_agent.py` — writer-stage handoff: Copilot primary,
    auto-falls back to an `@claude` comment if Copilot can't take the job,
    skips dispatch if an open issue/PR already targets the same folder or no
    topic resolved this run, and wraps raw feed-derived text in an explicit
    "untrusted external content" warning before it reaches the agent.
  - `audit_loop.py` (+ `aep-article-audit-loop.yml`) — the enforced retry
    loop: when `validate_article.py` fails on a PR, auto-posts an `@claude`
    fix-it comment with the exact failure, up to 3 attempts, then flags for
    a human instead of nagging forever.
  - `dispatch_publish.py` (+ `aep-notion-publish.yml`) — the real publisher
    stage: dispatched when a PR merges (merge = human approval), hands off
    to an agent turn that actually calls the Notion MCP tools per
    `aep/prompts/publisher.md`.
  - `dispatch_amplify.py` (+ `aep-amplify.yml`) — the amplification stage:
    dispatched once `publish-draft.json`'s `status` is confirmed
    `"Ready to Publish"` (the publisher's own bookkeeping PR merging), hands
    off to an agent turn that drafts a LinkedIn post per
    `aep/prompts/amplify.md`, applying `aep/prompts/brand-voice.md`'s house
    style. Drafts only — no LinkedIn API credential exists in this repo, so
    a human posts it themselves.
  - see `docs/agent-dispatch.md` for how the three agents are actually
    invoked (scheduled vs. manual vs. local).
  - `generate_hero_image.py` and `generate_infographic.py` (code-rendered
    hero images and concept-infographics, no external API).
  - `validate_article.py` — the publish-readiness gate for `articles/**`,
    run in CI via `aep-article-check.yml`: structure, hero/diagram/project
    presence, actually executes `project/`'s documented command, lints for
    AI-tell phrasing, requires an infographic once 3+ parallel concepts
    appear, and requires `topic-research-decision.json` (the real research
    pass — see below) before treating a draft as complete.
- `publisher/`: Notion draft template + field mapping, consumed by the
  publisher agent stage, not by a deterministic script.
- `policies/`: explicit external-LLM prohibition.

## How topics get picked — and why there's an agent stage, not just a script

`aep/pipelines/fetch_trend_signals.py` fetches live RSS/Atom feeds (config:
`pipelines/trend_sources.json`) every run — no static seed file, no LLM call,
no API key — and scores each item with plain, inspectable heuristics
(freshness/relevance/practicality). **This is a pre-filter, not a
researcher.** It has no judgment: it cannot tell a substantive engineering
post from vendor content-marketing that happens to share the same keywords,
and it cannot tell if a topic has already been covered elsewhere on the
internet (only against this repo's own `articles/**` history). It exists to
cheaply narrow ~60+ RSS items down to a short list for free — nothing more.

`run_pipeline.py`'s `resolve_topic()` applies one rule that governs series
pacing:
- **An active series' next part never gets its topic from trend ranking.**
  The title is fixed once, in that series's own `series_plan.json`, when the
  series starts. Trend data only supplies supporting evidence/timeliness for
  that already-committed title (`topic-discovery.json`'s
  `trend_support_strength` per run).
- **Only when there's no active series** does the top live-ranked,
  non-duplicate candidate become the proposed (standalone) topic.
- **De-duplication** excludes any live candidate too similar (Jaccard ≥ 0.6)
  to an already-published `articles/**` topic, computed fresh from repo
  state every run.

The real judgment happens one stage later, as an actual agent turn:
**`aep/prompts/trend-research-agent.md`** is required — mechanically, via
`validate_article.py`'s `check_topic_research_decision` — before any writing
starts. It's the agent (Copilot/Claude Code, with real web search) actually
researching the shortlist: checking credibility, depth, and whether the
angle is already done to death, and either confirming the deterministic
pick or overriding it with a better one from the shortlist — recorded in
`<article-dir>/topic-research-decision.json`
(`aep/schemas/topic-research-decision.schema.json`). The pre-filter narrows;
the agent decides.

**Pacing/idempotency**: `dispatch_to_agent.py` and `dispatch_publish.py`
both check for an existing open issue/PR targeting the same folder before
opening a new one — this, plus the human-approval gate on every PR, is what
actually controls how fast series parts ship, not how often the scheduled
workflow fires.

## The full agent chain, and the two loops that weren't enforced before

```
live feeds → heuristic pre-filter → TREND-RESEARCH AGENT (real judgment,
             (fetch_trend_signals)   topic-research-decision.json — gated)
                                            │
                                            ▼
                                     RESEARCH AGENT (research.md)
                                            │
                                            ▼
                                     WRITER AGENT (writer.md) — article,
                                     diagrams, hero/infographic, project/
                                            │
                                            ▼
                          ┌── AUDIT LOOP (aep-article-audit-loop.yml) ──┐
                          │  validate_article.py fails → auto @claude    │
                          │  fix-it comment, up to 3 attempts, then      │
                          │  flags for a human instead of nagging        │
                          └───────────────────────────────────────────┘
                                            │
                                            ▼
                                HUMAN APPROVAL (PR review + merge)
                                            │
                                            ▼
                     PUBLISHER AGENT (publisher.md) — actual Notion MCP
                     sync, dispatched by aep-notion-publish.yml on merge;
                     idempotent upsert keyed by external_id
                                            │
                                            ▼ (publish-draft.json status ->
                                               "Ready to Publish")
                     AMPLIFY AGENT (amplify.md) — drafts a LinkedIn post
                     (brand-voice.md house style), dispatched by
                     aep-amplify.yml; human posts it, no LinkedIn API here

```

Guardrails (schema validation, execution checks, style lint, the
no-external-LLM policy, the untrusted-external-content warning
`dispatch_to_agent.py` puts around raw feed text in every issue body) sit
around every stage above.

**Important limitation to keep in mind**: no deterministic script under
`aep/pipelines/` can ever call an MCP tool directly (Notion MCP included) —
MCP tools only exist inside an agent's own tool-use context. Every "MCP
integration" in this repo is therefore a dispatch (create an issue, get an
agent to pick it up) followed by an agent turn that has the right MCP tools
configured — never a raw API call embedded in a `.py` file with a stored
secret.

## Where finished articles live

Not under `aep/` — published/drafted articles live in `articles/<series>/part-NN/`
(series) or `articles/<slug>/` (standalone), each a hero image + content +
diagrams + a runnable mini-project. See `aep/prompts/writer.md` for the exact
required layout and `aep/pipelines/validate_article.py` for the mechanical check.

## Workflow schedule assumption
AEP workflow cron schedules use UTC:
- Morning research: `06:00 UTC`
- Evening review: `20:00 UTC`

## Future expansion
This v1 is intentionally stubbed for roadmap phases (trend/research engines, builder/writer/diagram agents, auditors/publisher, analytics loop) without affecting existing repository behavior.
