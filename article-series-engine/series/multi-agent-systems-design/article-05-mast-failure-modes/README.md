# Article 05 — Preventing the MAST failure modes by design, not by autopsy

Status: ready_for_review. Full text lives on this article's Notion page.

## Scope

For each MAST root category: the specific architectural decision (spec templates, handoff contracts, verifier checkpoints) that prevents it, with code - not a diagnostic checklist after the fact. Does not re-catalog all 14 MAST failure modes individually.

## Gap this closes

Nearly every "why multi-agent systems fail" post is a post-hoc listicle repeating the same MAST taxonomy stats. This maps MAST's 3 root categories to concrete design-time decisions and code, instead of restating the taxonomy.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues the disclosed illustrative DevPulse case study - same honest cap as Articles 01-04. |
| Clarity | 5/5 | One prevention per category, explicitly justified as covering more of the 14 modes than 14 individual patches would; explicit distinction drawn from Article 04 to avoid conflating authorization with correctness. |
| Proof density | 5/5 | Cemri et al. 2025 (MAST) grounded in its actual methodology (grounded theory, 150 traces, kappa=0.88, LLM-as-judge validation), not just the headline stats most other content stops at. |
| Visual support | 5/5 | One diagram mapping all three categories to their DevPulse-specific prevention, embedded directly as an SVG attachment. |
| Voice integrity | 5/5 | Matches established essay register, direct "you" address in practical sections, direct-challenge closing beat. |
| Usefulness | 5/5 | All three mechanisms shown working end-to-end as one pipeline (spec -> handoff -> verification), not three isolated demos; naive vs. verified pattern both executed for direct contrast. |
| **Total** | **28/30** | Same honest ceiling as Articles 01-04. |

## Word count

1,996 words - essentially at the 2,000-2,600 target floor.

## Diagram

MAST's three categories mapped to DevPulse-specific preventions:
https://lucid.app/lucidchart/2a7c8e99-b774-4e71-be31-e40e723281bb/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/mast_prevention_checks.py
```

Verified output: a vague spec (System Design Issues) is blocked at creation; an incomplete handoff (Inter-Agent Misalignment) is blocked even when the underlying spec was valid; the naive verification pattern (Task Verification) reports success on a crashed container while the verified pattern correctly reports failure with evidence.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
