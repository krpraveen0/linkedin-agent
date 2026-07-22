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
| Earned depth | 3/5 | A composite, well-specified, proof-testable case study - explicitly disclosed as illustrative, not claimed as personal lived experience. Structurally capped without a real anecdote - unchanged by voice calibration below. |
| Clarity | 5/5 | Topology claim is set up and paid off explicitly; code examples match the case study instead of contradicting it. |
| Proof density | 5/5 | Anthropic's published 3-10x token stat verified against the primary source, verified pairwise-link math, tested code, worked case-study walkthrough, References section added. |
| Visual support | 5/5 | Two load-bearing diagrams (decision tree + actual-topology-vs-full-mesh), each referenced and resolved in text. |
| Voice integrity | 5/5 | Calibrated against two real, fetched samples of Praveen's own Medium writing across different registers - an essay-style piece (zero contractions, short punchy paragraphs, numbered Attempt-1/Attempt-2 escalation) and a tutorial-style piece (contractions throughout, second-person, numbered steps). This article matches the essay register deliberately, since it is an argument/framework piece, not a tutorial - a reasoned genre match rather than a single blanket rule applied without checking. |
| Usefulness | 5/5 | Runnable checklist code, concrete Monday-morning action, worked example. |
| **Total** | **28/30** | Five axes maxed. Earned Depth remains the one honest gap - achieved by strengthening everything checkable, not by inflating the one axis that structurally requires a real anecdote to move. |

## Word count

1,601 words - inside the 1,600-2,000 target band.

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
