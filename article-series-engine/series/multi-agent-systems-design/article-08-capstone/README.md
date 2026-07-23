# Article 08 — Putting it together: designing a production multi-agent system end to end

Status: ready_for_review. Full text lives on this article's Notion page. This is the final article in the series.

## Scope

Capstone: one worked system, decision by decision, referencing every earlier article at the point that decision gets made. No new concepts - synthesis only.

## Gap this closes

Ties every prior article's decision into one worked design walkthrough - the thing none of the individual pattern/failure/governance posts researched for this series ever do, since they each cover one slice in isolation.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues the disclosed illustrative DevPulse case study - same honest cap as Articles 01-07. |
| Clarity | 5/5 | Seven gates walked in the actual order decisions get made, each tied to a specific numbered finding from its source article, not just a topic mention. |
| Proof density | 5/5 | No new sources needed (synthesis only, per scope) - instead, a consolidated bibliography of every primary source used across the series, and a direct proof that the seven mechanisms compose (the integrated pipeline), not just that each works alone. |
| Visual support | 5/5 | One diagram showing all seven gates as a single vertical pipeline against one real ticket, including the broken-variant branch. |
| Voice integrity | 5/5 | Matches established essay register; closing section carries deliberately more weight than prior articles' closings, appropriate for a series finale. |
| Usefulness | 5/5 | capstone_pipeline.py actually chains all seven mechanisms together and runs one real ticket through all of them, then proves the gates matter by running a second ticket that gets correctly blocked - composition is executed, not asserted. |
| **Total** | **28/30** | Same honest ceiling as Articles 01-07. |

## Word count

2,659 words - inside the 2,600-3,200 target band.

## Key addition beyond the other 7 articles

An honest "what this series did not cover" section - decentralized architectures, heterogeneous model teams, human-in-the-loop escalation, and production scale were all named directly as out of scope, rather than letting the capstone imply the series was exhaustive.

## Diagram

All seven gates as one pipeline against a real ticket, with the broken-variant branch:
https://lucid.app/lucidchart/02e887e0-0b23-4847-809c-af2fbb04fc22/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/capstone_pipeline.py
```

Verified output: PAY-402 passes all seven gates in sequence, ending in a verified (not assumed) running container; PAY-403, with a deliberately incomplete handoff, is correctly blocked at Gate 5, and Gates 6-7 never run for it.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied. This closes out the eight-article series.
