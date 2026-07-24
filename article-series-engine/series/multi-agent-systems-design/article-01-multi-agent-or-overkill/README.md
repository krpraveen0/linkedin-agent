# Article 01 — Multi-agent or overkill? A decision framework before you add a second agent

Status: PILOT REWRITE, addressing real rejection feedback from Medium publishers. Full text on this article's Notion page.

## Why this got rewritten

All eight articles in this series were submitted to Medium publishers and rejected, with no reason given. Rather than treat the previous 28/30 self-scored version as sufficient, this rewrite addresses three concerns raised directly, and does not assume the fix is correct until it is judged against real editorial standards, not this project's own rubric.

## What actually changed

1. **Case study swapped**: DevPulse (a personal dev-productivity daemon) replaced with ClaimGuard (an insurance claims and fraud-detection system) - genuinely higher stakes, and thematically closer to real financial-services work than a consumer tool.
2. **Beginner on-ramp added**: a short, plain-language paragraph up front for readers with zero prior AI agent knowledge, pointing to the companion Fundamentals of AI Agents series for the full foundation.
3. **Self-referential meta-commentary removed**: previous articles in this series included lines like "the first version of this code had a bug, here's how I caught it" directly in the article body - a real, specific AI-writing tell. None of that appears in this rewrite.
4. **Repetitive tell-phrases removed**: "worth naming," "worth being honest," "worth sitting with," and the "Not X. It's Y." fragment construction were used constantly across the original 13 articles. Grep-verified zero occurrences in this rewrite.
5. **Genuine infographic instead of an architecture diagram**: icon-cards, verdict badges, and large stat callouts, replacing the boxes-and-arrows flowchart style used in every previous diagram in this project.
6. **Structural variation**: this article's section order and rhythm are not identical to the rigid template every prior article used - closings, in particular, no longer follow the same fixed formula.

## What did NOT change

The core teaching content (the three-question framework, the coordination-cost math, Anthropic's real citation) is the same underlying material - it was the presentation, not the substance, that needed the most work. Earned Depth remains honestly capped: ClaimGuard is still a disclosed, illustrative case study, not something that actually happened to Praveen.

## Setup

No dependencies beyond the Python standard library.

## Run

```bash
python src/agent_decision_calculator.py
```

Verified output: ClaimGuard's three parallel agents (intake, fraud-risk, policy-verification) correctly justify multi-agent for reason two; the fraud-risk-to-payment-processing relationship correctly justifies it for reason three instead; a proposed unnecessary sixth agent correctly fails the test.

## Open question

This is a pilot. It has not yet been judged against a real editorial standard - only against the same kind of internal review that produced a version that got rejected. The honest thing to do is treat this as unproven until there's a real signal it worked better, not to re-score it 28/30 and move on.
