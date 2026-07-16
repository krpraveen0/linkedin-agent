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
1. Never publish unexecuted code.
2. Prefer official documentation.
3. Every article teaches by building.
4. Every diagram is editable.
5. Every claim is referenced.
6. Quality over virality.
7. Human approval before publication.

## v1 scope in this folder
- `docs/`: concise implementation blueprint (`implementation-spec.md`) and
  the agent-dispatch guide (`agent-dispatch.md`).
- `schemas/`: contracts for AEP artifacts.
- `prompts/`: agent role templates — read by whichever agent (Copilot,
  Claude Code, opencode) is running the generative step; the contracts are
  the same regardless of which one you use.
- `pipelines/`: deterministic trend/research/audit pipeline
  (`run_pipeline.py`, `validate_artifacts.py`) plus the agent handoff
  (`dispatch_to_agent.py`: Copilot primary, auto-falls back to an `@claude`
  comment if Copilot can't take the job) — see `docs/agent-dispatch.md` for
  how the three agents are actually invoked (scheduled vs. manual vs. local) — plus
  `generate_hero_image.py` (code-rendered hero images, no external API) and
  `validate_article.py` (the publish-readiness gate for `articles/**`,
  also run in CI via `aep-article-check.yml`).
- `publisher/`: Notion draft template + field mapping.
- `policies/`: explicit external-LLM prohibition.

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
