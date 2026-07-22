# Article 06 — Observability and evaluation for multi-agent systems: what to actually measure

Status: ready_for_review. Full text lives on this article's Notion page.

## Scope

What to trace (per-agent decisions, tool selection accuracy, handoff points), minimal cost/latency budgets, and a lightweight eval harness you can run without adopting a third-party platform.

## Gap this closes

Most eval content is either academic benchmarks or a vendor-platform pitch. This is a practitioner's minimal-viable observability stack grounded in the real OpenTelemetry GenAI standard, not a product.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues the disclosed illustrative DevPulse case study - same honest cap as Articles 01-05. |
| Clarity | 5/5 | The article's central claim (trace context breaks at blackboard hops) is derived directly and explicitly from Article 02's own finding, not asserted independently. |
| Proof density | 5/5 | OpenTelemetry GenAI semantic conventions, verified across multiple current sources (CNCF graduation date, span names, actual attribute names, stability opt-in env var) - not a vendor's marketing page. |
| Visual support | 5/5 | One diagram directly contrasting connected vs. broken trace propagation for the same real task, with the exact per-span budget numbers used in the code. |
| Voice integrity | 5/5 | Matches established essay register, direct "you" address in practical sections, three-part direct-challenge closing beat. |
| Usefulness | 5/5 | Four runnable checks (trace connectivity, latency budget, token budget, tool-selection accuracy) - the eval harness genuinely fails (33% accuracy) on a deliberately naive selector, shown executing, not just described. |
| **Total** | **28/30** | Same honest ceiling as Articles 01-05. |

## Word count

1,806 words - inside the 1,800-2,200 target band.

## Diagram

Connected vs. broken trace propagation for DevPulse's classifier-provisioner handoff:
https://lucid.app/lucidchart/f745b898-4426-4608-9cbe-e3e922966105/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/minimal_observability_harness.py
```

Verified output: connected spans correctly report one shared trace_id; the broken variant correctly reports two disconnected trace_ids; a token-budget violation is correctly flagged; a deliberately naive tool selector scores 33% accuracy with two named, concrete failures.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
