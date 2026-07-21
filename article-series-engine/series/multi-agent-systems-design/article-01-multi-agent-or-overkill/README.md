# Article 01 — Multi-agent or overkill? A decision framework before you add a second agent

Status: drafted (does NOT pass the SIGNAL quality gate yet - see below). Notion manifest is the source of truth for current status.

## Scope

When a second agent is genuinely justified vs. added complexity for no
reason. A single-agent baseline test, a coordination-cost model, and a
concrete go/no-go checklist.

## Gap this closes

Most guides assume you need multi-agent from the start. Almost none give a
rigorous "should you even do this" framework grounded in real
coordination-cost data (e.g. 4 agents = 6 potential failure points, 10 = 45).

## SIGNAL rubric scorecard (self-scored, see praveen-technical-article-writer skill)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 2/5 | **FAILS** - no real personal anecdote yet, placeholder marked in draft, not fabricated |
| Clarity | 4/5 | |
| Proof density | 4/5 | Anthropic's published 3-10x token stat, verified pairwise-link math, tested code |
| Visual support | 4/5 | One decision-tree diagram for ~900 words |
| Voice integrity | 3/5 | Approximated against skill rules, not verified against Praveen's actual voice |
| Usefulness | 5/5 | Runnable checklist code, concrete Monday-morning action |
| **Total** | **22/30** | **Below the 24/30 gate, and Earned Depth is below the 3/5 floor** |

**Does not pass the gate.** Per the skill's own non-negotiable rule, a
missing anecdote gets flagged, not invented. Needs Praveen's real detail
before this moves to ready_for_review.

## Word count

876 words (draft) against a 1,600-2,000 target - under target, expected to
grow once the real anecdote is added.

## Diagram

Decision-tree flowchart built in Lucid:
https://lucid.app/lucidchart/650f7c3a-7b13-426f-94da-664f1929c2fe/edit
(kept as Lucid for now - draw.io was requested but no draw.io connector is
available; a hand-authored .drawio XML source is an option for a future
pass if preferred over Lucid's PNG-plus-edit-link approach)

## Setup

No dependencies beyond the Python standard library (3.9+ for the `tuple[bool, str]` type hint).

## Run

```bash
python src/agent_decision_calculator.py
```

Verified output includes the coordination-link table (1–10 agents) and an
interactive go/no-go checklist. Also verified programmatically:
`pairwise_coordination_links(4) == 6` and `pairwise_coordination_links(10) == 45`.

## Published article

Not yet - blocked on the Earned Depth gate above.
