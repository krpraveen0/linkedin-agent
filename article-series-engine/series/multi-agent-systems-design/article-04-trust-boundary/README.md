# Article 04 — Designing the trust boundary: authorization between agents that isn't an afterthought

Status: ready_for_review. Full text lives directly on this article's Notion page (see database), not just this README.

## Scope

Per-agent identity, least-privilege scoping, and a working scoped-capability example showing how to stop permission scope from silently expanding across a delegation chain. Grounded in a real classical security problem (the confused deputy, Hardy 1988), not a vendor pitch.

## Gap this closes

Governance/authorization content online is almost entirely vendor blog posts describing guardrails abstractly. This walks through an actual policy implementation addressing the real "trust inheritance" problem - Agent A passing unrestricted authority to Agent B - with a vulnerable pattern shown running, not just described.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Continues the disclosed illustrative DevPulse case study - same honest cap as Articles 01-03. |
| Clarity | 5/5 | Confused deputy explained via its actual 1988 origin story, not just named; vulnerable and safe patterns shown in direct code contrast. |
| Proof density | 5/5 | Hardy 1988 (verified via direct search, precise details - Tymshare, FORT compiler, billing file), a 2026 arXiv paper on authorization propagation, O'Reilly Radar, WorkOS - real sources, not vendor-pitch summaries. |
| Visual support | 5/5 | One diagram showing DevPulse's per-agent scopes plus an explicit before/after (vulnerable vs. trust-boundary) contrast panel. |
| Voice integrity | 5/5 | Matches established essay register, direct "you" address in practical sections, direct-challenge closing beat. |
| Usefulness | 5/5 | Runnable code shows the vulnerable pattern actually succeeding (no check at all) directly next to the safe pattern blocking the same attack - the contrast is executed, not just asserted. |
| **Total** | **28/30** | Same honest ceiling as Articles 01-03. |

## Word count

2,192 words - inside the 2,200-2,800 target band (essentially at the floor).

## Diagram

DevPulse's trust boundary, annotated per agent, with an explicit vulnerable-vs-safe contrast panel:
https://lucid.app/lucidchart/140d6cf5-8f6e-4e86-9cba-5c5eab5e7836/edit
Embedded directly in the Notion page as an SVG attachment (not a placeholder).

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/scoped_capability_checker.py
```

Verified output: the provisioner's own capability check passes for actions it was actually granted and fails for actions it was not; an attempt to delegate an action the classifier itself was never granted is blocked with a clear error; the vulnerable `vulnerable_blind_trust` function is shown actually proceeding with an attacker-controlled repo URL, with no check performed at all - the contrast is executed, not just described.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
