# Article 03 — The four canonical orchestration patterns, and how to actually choose one

Status: ready_for_review. Notion manifest is the source of truth for current status.

## Scope

Runnable code for each of the four patterns, a decision tree for picking one based on task shape, and the trade-offs most guides gloss over. Pattern selection only - authorization (04), failure-mode prevention (05), and evaluation (06) are separate articles.

## Gap this closes

Multiple sources list sequential/parallel/hierarchical/decentralized patterns, but none give a decision procedure plus real runnable code for each - description without implementation. This article also does something none of the researched competing content does: grounds the decision procedure in a real controlled study (Google Research, 180 configurations) instead of convention or a framework's tutorial defaults.

## An honest note on scope

Research for this article surfaced that current industry writing mostly converges on five or six named patterns (adding "handoff" and "debate/loop" to the four this article uses), not four. The article addresses this directly rather than silently picking four and hoping nobody notices the discrepancy - it argues handoff and debate are compositions of the four control-flow topologies, not new ones, and makes that case explicitly in the text.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues the disclosed illustrative DevPulse case study - same honest cap as Articles 01 and 02. |
| Clarity | 5/5 | The four-vs-six-patterns tension is addressed head-on rather than avoided; DevPulse's four relationships are named individually rather than forcing one label on the whole system. |
| Proof density | 5/5 | Grounded in a real, verified primary source (Google Research's own blog, fetched directly, not a secondary paraphrase) with exact figures (80.9% gain, 39-70% degradation, 17.2x vs 4.4x error amplification, 87% predictive accuracy) - a genuinely different tier of evidence than the competing content researched for this series. |
| Visual support | 5/5 | One diagram comparing all four patterns side by side, each annotated with DevPulse's actual relationship and the study's real numbers where applicable. |
| Voice integrity | 5/5 | Matches the established essay register (zero contractions outside a verbatim series-index title, direct "you" address in practical sections, direct-challenge closing beat before the series index). |
| Usefulness | 5/5 | Runnable recommender distinguishes three concrete cases (DevPulse's parallel batch, its sequential handoff, and a hypothetical high-stakes finance task) with different verdicts for the same "independent subtasks" property, depending on error cost - the nuance most guides skip. |
| **Total** | **28/30** | Same honest ceiling as Articles 01 and 02. |

## Word count

2,216 words - inside the 2,200-2,800 target band.

## Key source

Kim, Y. and Liu, X., "Towards a Science of Scaling Agent Systems," Google Research, January 2026 - fetched directly from research.google/blog, not taken from a secondary summary. Paper: https://arxiv.org/abs/2512.08296

One number (the "three-to-four-agent" team-size limit) is attributed to a researcher interview reported by a secondary source (VentureBeat), not verified directly in the primary blog post - flagged as such in the article text rather than presented as equally strong evidence.

## Diagram

Four-pattern comparison, annotated with DevPulse's relationships and the study's real numbers:
https://lucid.app/lucidchart/c1d3f41f-528d-44b4-abd5-64a394945e7b/edit

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/orchestration_pattern_recommender.py
```

Verified output: DevPulse's parallel batch recommends "parallel," the classifier-provisioner handoff recommends caution around sequential multi-agent splitting, and a high-stakes finance variant with the same independence property recommends "hierarchical" instead - confirming the recommender responds to error-cost, not just task shape.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
