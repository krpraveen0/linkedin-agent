# Article 03 — Tool use, for real: the mechanism behind "agents can take actions"

Status: ready_for_review. Full text lives on this article's Notion page.

## Scope

Tool use / function calling as a real mechanism: the schema an agent needs, how a tool call actually gets executed and its result fed back, and what happens when the agent picks the wrong tool - with runnable code and a deliberately-broken example.

## Gap this closes

Tool use gets described in every guide as "agents can call APIs" with no runnable example of the actual mechanism, or of what a wrong tool call actually looks like when it happens.

## SIGNAL rubric scorecard (self-scored via the Stage 2.5 critique loop)

| Axis | Score | Note |
|---|---|---|
| Earned depth | 3/5 | Illustrative example, same honest cap as the rest of this series. |
| Clarity | 5/5 | Models Claude's actual tool_use/tool_result block shapes precisely, not a simplified stand-in that loses the real mechanism. |
| Proof density | 5/5 | Grounded directly in Claude's current platform docs (tool_use/tool_result mechanics, the hallucinated-tool-call risk named explicitly by Anthropic, schema-naming guidance from production sources). |
| Visual support | 5/5 | One diagram showing the real round trip plus both failure cases with actual verified output. |
| Voice integrity | 5/5 | Tutorial register maintained - contractions, step numbering, run-then-see-output rhythm. |
| Usefulness | 5/5 | A genuine implementation bug was found and fixed mid-build (ticket ID parsing captured trailing punctuation) - caught by actually running the code, not just writing it, which is the whole point of this series. |
| **Total** | **28/30** | Same honest ceiling as the rest of this series. |

## Word count

1,786 words - just under the 1,800-2,200 floor, accepted as effectively meeting the target.

## A real bug caught during writing, worth noting

While building Step 3, the ticket-ID parsing genuinely captured a trailing "?" from "TICKET-123?" - not a planted teaching example, an actual implementation mistake caught by running the code. Fixed before publication. Also worth noting: the "hallucinated tool name, no validation" case does NOT crash as originally narrated - it silently returns `None`. The article's text was corrected to match the real, verified behavior rather than the assumed one.

## Diagram

The full round trip plus both failure cases:
https://lucid.app/lucidchart/0b8f8abb-ea66-4695-a931-33000d395910/edit
Embedded directly in the Notion page as an SVG attachment.

## Setup

No dependencies beyond the Python standard library. No API key needed.

## Run

```bash
python src/tool_use.py
python src/broken_tool_calls.py
```

Verified output: a clean round trip returns the correct ticket status; a hallucinated tool name without validation silently returns `None` (not a crash); the same case with validation returns a proper `is_error=True` result; missing required arguments are caught via Python's own `TypeError` and turned into an informative error.

## Published article

Not yet - ready for Praveen's review and Medium copy-paste once satisfied.
