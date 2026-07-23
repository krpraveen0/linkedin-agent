# Article 05 — Reactive vs. planning agents, and how to actually choose

Status: ready_for_review. Full text lives on this article's Notion page.

## Scope

Reactive (decide-one-step-at-a-time) vs. upfront planning (decide-the-whole-sequence-first) vs. a hybrid - a decision procedure for which fits a given task, not just a description of both, with runnable code for each.

## Gap this closes

Guides mention ReAct-style reactive agents and planner-style agents as two named things without a procedure for choosing between them - description without a decision framework, mirroring the gap the Design Multi-Agent Systems series closed for orchestration patterns, now at the single-agent level.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Illustrative examples, same honest cap as the rest of this series. |
| Clarity | 5/5 | All three approaches (reactive, planning, hybrid) get real code and real counted output, not just prose description - including the "why not just replan" question addressed directly. |
| Proof density | 5/5 | Grounded in both ReAct and ReWOO (Xu et al., 2023) with ReWOO's actual three-role architecture (Planner/Worker/Solver) explained, not just cited. |
| Visual support | 5/5 | One diagram showing both decisive cases plus the decision procedure itself, all with real counted numbers. |
| Voice integrity | 5/5 | Tutorial register maintained. |
| Usefulness | 5/5 | Decision-maker call counts are real and countable (4 vs 1 vs 2), not estimated - readers can apply the same counting exercise to their own systems directly. |
| **Total** | **28/30** | Same honest ceiling as the rest of this series. |

## Word count

2,042 words - inside the 2,000-2,400 target band.

## Diagram

Both decisive cases plus the decision procedure:
https://lucid.app/lucidchart/8616e1a8-63a5-476a-aa51-e792e9f49534/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library. No API key needed.

## Run

```bash
python src/efficiency_case.py
python src/adaptability_case.py
python src/hybrid_case.py
```

Verified output: the efficiency case shows 4 reactive calls vs. 1 planning call for identical results; the adaptability case shows planning committing to the wrong action ("restart") when the server is actually fine, while reactive correctly does nothing; the hybrid case shows 2 calls - planning the independent fetches, staying reactive only for the one genuine branch point.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
