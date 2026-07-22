# Article 02 — The coordination primitives: control, state, and communication — a vendor-neutral model

Status: ready_for_review. Notion manifest is the source of truth for current status.

## Scope

Three axes every multi-agent design decision reduces to: who controls sequencing, where state lives, how agents communicate (shared blackboard vs message passing vs direct calls). Framework-agnostic terminology used by every later article in the series.

## Gap this closes

Existing pattern guides mix the underlying model with a single vendor/framework (ADK-only, LangGraph-only). This builds the neutral mental model first, grounded in a real, current orchestration-architecture paper rather than one vendor's tutorial defaults.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues Article 01's disclosed illustrative case study (DevPulse) rather than a real personal anecdote - same honest cap as Article 01, for the same reason. |
| Clarity | 5/5 | Three axes established, then applied concretely to the same case study readers already know from Article 01 - no new unexplained jumps. |
| Proof density | 5/5 | Anthropic's guide, a real 2026 orchestration-architecture paper (control/state/communication components matched almost exactly), MCP and A2A's actual documentation, and genuine academic history (HEARSAY-II, 1971-1976) for the blackboard pattern - verified via direct fetch, not recalled from memory. |
| Visual support | 5/5 | Two diagrams: the three-axis model itself, and DevPulse's topology re-annotated with axis labels, directly continuing Article 01's diagram rather than starting fresh. |
| Voice integrity | 5/5 | Matches Article 01's essay register (argument/framework piece, not a tutorial) per voice-reference-notes.md - zero contractions (grep-verified), direct "you" address in practical sections, direct-challenge closing beat before the series cross-link. |
| Usefulness | 5/5 | Runnable classifier code distinguishes patterns that look similar but are not (supervisor-mediated vs. classic blackboard), catches an inconsistent design (decentralized control + direct calls) automatically. |
| **Total** | **28/30** | Same honest ceiling as Article 01 - five axes maxed, Earned Depth capped without a real anecdote. |

## Word count

1,897 words - inside the 1,800-2,200 target band.

## Medium reader-experience pass

Caught the same issue Article 01's first draft had: the closing section trailed into series navigation without a direct beat aimed at the reader first. Fixed by adding a direct challenge before the cross-link, matching the pattern documented in `voice-reference-notes.md`.

## Diagrams

1. Three-axis model (control / state / communication), with DevPulse's answers annotated per axis:
   https://lucid.app/lucidchart/e9ec7014-ed86-4ef0-8caa-11fd913a658e/edit
2. Article 01's topology diagram is referenced directly rather than rebuilt - continuity across the series.

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/coordination_model_classifier.py
```

Verified output: DevPulse's parallel agents classify as "Supervisor-dispatched local agents," the classifier-provisioner handoff classifies as "Supervisor-mediated blackboard," and an internally inconsistent design (decentralized control + direct calls) gets flagged automatically rather than silently accepted.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
