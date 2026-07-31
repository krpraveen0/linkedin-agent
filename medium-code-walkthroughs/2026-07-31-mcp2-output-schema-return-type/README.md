# mcp 2.0: your tool's return type builds its outputSchema

Code for the article **"mcp 2.0 Builds Your Tool's outputSchema From Its Return Type. A `-> int` Ships as `{\"result\": 5}`."** (2026-07-31).

`output_schema_probe.py` registers five tools with five different return annotations and, using only in-process calls (no model, no API key, no network), shows:

1. The `outputSchema` mcp 2.0's `MCPServer` generates from each return annotation — which get **wrapped** under a `result` key, which become open maps, which become plain objects, and which get no schema at all.
2. What a structured tool result actually puts on the wire: both a text `content` block (backwards compatibility) and `structuredContent`.
3. That a return value which violates the declared return type is rejected with a `ToolError` at the server, before the client sees it.

## Setup and run

```bash
python3 -m venv venv && . venv/bin/activate
pip install "mcp==2.0.0"
python3 output_schema_probe.py
```

Tested on `mcp==2.0.0` (published to PyPI 2026-07-28), `pydantic==2.13.4`, and Python 3.11.

## Real captured output

```
=== 1. outputSchema generated from each return annotation ===
add      -> title='addOutput'        fields=['result']
prices   -> title='pricesDictOutput' fields=additionalProperties=True
quote    -> title='Quote'            fields=['symbol', 'usd']
note     -> title='noteOutput'       fields=['result']
legacy   -> outputSchema: None (unstructured)

=== 2. what the server actually puts on the wire ===
add      content(text)='5'                  structuredContent={'result': 5}
prices   content(text)='{\n  "apple": 3,\n  "pear": 5\n}' structuredContent={'apple': 3, 'pear': 5}

=== 3. a return that violates the declared schema is rejected here ===
ToolError: Error executing tool bad: 1 validation error for DictModel
```

The output was independently reproduced byte-for-byte in a fresh virtualenv as part of the article's fact-check.

## Files

- `output_schema_probe.py` — the runnable probe.
- `article.md` — the full article.
- `figure1-annotation-to-schema.svg` — how each return annotation maps to a schema shape.
- `figure2-wire-and-validation.svg` — the result payload and the server-side validation gate.
