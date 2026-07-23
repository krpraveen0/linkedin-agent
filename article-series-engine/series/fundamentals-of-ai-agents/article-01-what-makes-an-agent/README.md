# Article 01 — What actually makes something an agent? A testable definition, not an analogy

Status: ready_for_review. Full text lives on this article's Notion page.

## Register note

This series uses the TUTORIAL register (contractions, heavy step-numbering, "run this now" checkpoints), not the essay register the Design Multi-Agent Systems series used - see `voice-reference-notes.md` at the package root for the reasoning.

## Scope

A testable definition of an agent: the observe-decide-act loop plus autonomy over next-step selection, distinguished concretely from a single prompt call and from a fixed workflow/RAG pipeline - with a runnable check, not just an analogy.

## Gap this closes

Every existing guide defines agents via analogy with no way to actually test whether a given system qualifies. This closes it with a runnable definitional test (`is_agentic`).

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Illustrative example (toy inbox agent), not a real personal anecdote - same honest cap as the other series for the same reason. |
| Clarity | 5/5 | Each of the three systems (workflow, fake loop, real agent) is built and run before the next is introduced - the reader sees the failure of each wrong answer before the right one. |
| Proof density | 5/5 | Grounded directly in Anthropic's own "Building Effective Agents" (fetched primary source), honestly flagging that even Anthropic's own terminology has reasonable critics, rather than presenting one definition as uncontested. |
| Visual support | 5/5 | One diagram showing all three systems' actual test results side by side. |
| Voice integrity | 5/5 | Deliberately tutorial register - contractions, direct step-by-step numbering, explicit code-then-run-then-see-output rhythm throughout, matching the real "uv" sample's register from voice-reference-notes.md. |
| Usefulness | 5/5 | Zero API key required - every step runs immediately as written, verified by actual execution multiple times before being written into the article. Step 6 shows the real-model extension without requiring it for the core lesson. |
| **Total** | **28/30** | Same honest ceiling as the other series, for the same reason (Earned Depth). |

## Word count

1,663 words - inside the 1,600-2,000 target band.

## Diagram

All three systems tested side by side:
https://lucid.app/lucidchart/616bcf16-4d7b-460f-9387-db33e1a2ac41/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library. No API key needed.

## Run

```bash
python src/step1_workflow.py
python src/step2_fake_loop.py
python src/step3_real_agent.py
python src/step4_the_test.py
```

Verified output: the workflow and fake loop both produce identical action sequences regardless of environment (agentic: False); the real agent produces a genuinely different, shorter sequence when there's nothing to do (agentic: True).

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
