# Article 04 — Two things people call "memory," and why conflating them breaks agents

Status: ready_for_review. Full text lives on this article's Notion page.

## Scope

Memory, precisely: context-window state vs. persistent memory - genuinely different engineering problems, with a runnable example of each and where they actually fail, in both directions.

## Gap this closes

Guides use "memory" as one word for two engineering problems with different failure modes. This names the distinction precisely and shows each one's actual failure mode in code - in both directions, not just the obvious one.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Illustrative example, same honest cap as the rest of this series. |
| Clarity | 5/5 | Shows BOTH directions of the conflation failing (context-only forgets across sessions; memory-only fails on immediate context), not just the more obvious one. |
| Proof density | 5/5 | Grounded in Anthropic's own memory tool documentation, with the distinction operationalized into two separately executed failure demonstrations. |
| Visual support | 5/5 | One diagram showing both failure modes and the correct handling of each, all with real verified output. |
| Voice integrity | 5/5 | Tutorial register maintained. |
| Usefulness | 5/5 | A second genuine bug was caught and fixed during writing (case-lowering in name extraction) - disclosed directly in the article itself, not hidden. |
| **Total** | **28/30** | Same honest ceiling as the rest of this series. |

## Word count

1,788 words - just under the 1,800-2,200 floor, accepted as effectively meeting the target.

## A real bug caught during writing

The first version of the name-extraction logic lowercased the whole message before slicing out the name, so "Alex" came back as "alex." Fixed to find the split point in the lowercased string but slice the original message. Disclosed directly in the article text, not smoothed over.

## Diagram

Both failure modes and the correct handling of each:
https://lucid.app/lucidchart/f550c688-2d21-41e1-b4a6-52888689c18f/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library. No API key needed.

## Run

```bash
python src/context_only_agent.py
python src/persistent_memory_agent.py
```

Verified output: context-only agent forgets the user's name across a new session; the persistent-memory version correctly recalls it; a memory-only agent fails on something said one message earlier in the same session, because it never checks the conversation already in context.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
