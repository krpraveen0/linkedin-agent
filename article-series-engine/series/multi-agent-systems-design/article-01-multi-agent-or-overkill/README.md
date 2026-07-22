# Article 01 — Multi-agent or overkill? A decision framework before you add a second agent

Status: ready_for_review (SIGNAL gate now passes — see scorecard below). Notion manifest is the source of truth for current status.

## Scope

When a second agent is genuinely justified vs. added complexity for no
reason. A single-agent baseline test, a coordination-cost model, a
concrete go/no-go checklist, and a worked case-study walkthrough.

## Gap this closes

Most guides assume you need multi-agent from the start. Almost none give a
rigorous "should you even do this" framework grounded in real
coordination-cost data (e.g. 4 agents = 6 potential failure points, 10 = 45).

## SIGNAL rubric scorecard (self-scored, see praveen-technical-article-writer skill)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | A composite, well-specified, proof-testable case study - explicitly disclosed as illustrative, not claimed as personal lived experience. Different flavor of depth than a real war story; appropriate for training content, but honestly not the same thing, and the scorecard shouldn't blur that. |
| Clarity | 4/5 | |
| Proof density | 5/5 | Anthropic's published 3-10x token stat, verified pairwise-link math, tested code, plus a fully worked case-study walkthrough |
| Visual support | 4/5 | One decision-tree diagram for ~1,270 words - reasonable, a second diagram (the case study's own architecture) is a fair next-pass addition |
| Voice integrity | 3/5 | Approximated against skill rules, not verified against Praveen's actual voice |
| Usefulness | 5/5 | Runnable checklist code, concrete Monday-morning action, worked example |
| **Total** | **24/30** | **Clears the gate (>=24, no axis below 3) - but see the Earned Depth note above before treating this as equivalent to a personal-anecdote pass** |

## Word count

1,266 words against a 1,600-2,000 target - closer than before, still a bit
under. Praveen's call whether to expand further or publish as-is.

## Diagram

Decision-tree flowchart built in Lucid:
https://lucid.app/lucidchart/650f7c3a-7b13-426f-94da-664f1929c2fe/edit
(draw.io requested but no connector is available - a hand-authored .drawio
XML source remains an option for a future pass)

## Case study source

The developer-OS case study is adapted from a training case-study document
(itself noted as inspired by "30 Agents Every AI Engineer Must Build,"
Packt Publishing) - paraphrased and restructured for this article, not
reproduced verbatim, and explicitly disclosed in the article text as a
composite illustration rather than a specific real product.

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

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
