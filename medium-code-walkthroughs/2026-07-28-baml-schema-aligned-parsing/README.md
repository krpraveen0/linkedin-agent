# BAML Schema-Aligned Parsing — runnable walkthrough

Companion code for the 2026-07-28 article *"BAML's Schema-Aligned Parser Reads
LLM Output That json.loads() Can't — Here's Exactly What It Coerces."*

Everything here runs **fully offline**. `b.parse.FunctionName()` invokes only
BAML's parser — it never calls a model, so no API key is needed.

## Files

- `baml_src/triage.baml` — the schema (a `Ticket` class, a `Priority` enum, and a `TriageTicket` function).
- `sap_vs_jsonloads.py` — feeds a messy model response to `json.loads()` (fails) and to `b.parse.TriageTicket()` (succeeds + coerces types).
- `sap_boundaries.py` — shows where SAP refuses: an unmappable enum value and a missing required field both raise `BamlError`.
- `figure1-two-schools.svg`, `figure2-coercions.svg` — the article's diagrams.

## Setup

```bash
pip install baml-py==0.223.0 pydantic typing_extensions
baml-cli generate        # regenerates baml_client/ from baml_src/
```

`baml_client/` is generated code; if it is missing, run `baml-cli generate`.
The `baml-cli` binary ships inside the `baml-py` wheel.

Verified on: `baml-py` 0.223.0 (released 2026-06-23), Python 3.11.15, Linux.

## Run

```bash
python3 sap_vs_jsonloads.py
python3 sap_boundaries.py
```

## Captured output

### `python3 sap_vs_jsonloads.py`

```
=== json.loads() ===
JSONDecodeError -> Expecting value: line 1 column 1 (char 0)

=== b.parse.TriageTicket() ===
returned: Ticket
priority   -> <Priority.High: 'High'>   ( Priority )
effort_days-> 2         ( int )
tags       -> ['billing']      ( list )
summary    -> Checkout page returns 500 on payment submit
```

### `python3 sap_boundaries.py`

```
=== enum value not in schema ('urgent') ===
BamlError -> Failed to coerce value: ParsingError { scope: [], reason: "Failed while parsing required fields: missing=0, unparsed=1", causes: [ParsingError { scope: [], reason: "Failed to parse field priority: priority: Expected Priority enum value, got String(\"urgent\", Complete).", causes: [ParsingError { scope: ["priority"], reason: "Expected Priority enum value, got String(\"urgent\", Complete).", causes: [] }] }] }

=== required field 'summary' absent ===
BamlError -> Failed to coerce value: ParsingError { scope: [], reason: "Failed while parsing required fields: missing=1, unparsed=0", causes: [ParsingError { scope: [], reason: "Missing required field: summary", causes: [] }] }
```

## What to notice

`json.loads()` fails at character 0 because the response opens with prose, not
`{`. SAP reads the string toward the declared type: `"high"` becomes the enum
member `Priority.High`, `"2 days"` becomes the int `2`, and the lone string
`"billing"` becomes the list `['billing']`. It bends format and type — but not
meaning: an enum value with no schema match (`"urgent"`) and a missing required
field both raise `BamlError`.
