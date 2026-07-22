# Article 07 — Shared-resource contention: when your agents fight over the same database row

Status: ready_for_review. Full text lives on this article's Notion page.

## Scope

A real double-booking/race-condition scenario between two agents, diagnosed and fixed with explicit leasing/locking code - not just "add a database."

## Gap this closes

Connection-pool exhaustion and double-booking failures are mentioned in passing by a couple of articles, but nobody walks through a concrete concurrency-control fix with runnable code.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues the disclosed illustrative DevPulse case study - same honest cap as Articles 01-06. |
| Clarity | 5/5 | Explicitly distinguishes the lost-update anomaly demonstrated here from deadlock (Dining Philosophers), rather than conflating the two; names optimistic vs. pessimistic locking and justifies the choice. |
| Proof density | 5/5 | CoAgent (2026) and DPBench (2026) both fetched and verified, with a direct citation chain back to Article 05's own MAST source; Dijkstra 1965 grounds the classical theory precisely. |
| Visual support | 5/5 | One diagram showing the naive race and the atomic fix side by side, with the actual rowcount-based verification logic shown. |
| Voice integrity | 5/5 | Matches established essay register, direct "you" address in practical sections, three-part direct-challenge closing beat. |
| Usefulness | 5/5 | The race condition is not simulated or narrated - it is a real SQLite file and real Python threads, reproduced across 5+ runs to confirm reliability before writing the claim into the article. |
| **Total** | **28/30** | Same honest ceiling as Articles 01-06. |

## Word count

1,814 words - inside the 1,800-2,200 target band.

## Diagram

Naive race vs. atomic fix, side by side, with the actual verification logic:
https://lucid.app/lucidchart/f4a523a1-0585-4854-abe7-14137678863f/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/port_lease_race.py
```

Verified output (run 5+ times to confirm reliability, not luck): the naive allocator reliably produces a double-booked port with no exception or SQL error; the atomic conditional-UPDATE version reliably allocates two different ports to the same two concurrent callers.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
