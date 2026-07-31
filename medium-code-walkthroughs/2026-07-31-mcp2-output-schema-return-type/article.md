# mcp 2.0 Builds Your Tool's outputSchema From Its Return Type. A `-> int` Ships as `{"result": 5}`.

Write an MCP tool that returns an integer, and you might expect the number to travel to the client as, well, a number. It doesn't. On the wire it becomes `{"result": 5}` — a JSON object with a single `result` key — plus a matching `outputSchema` that the server generates from your return annotation and hands to the client before the tool is ever called.

That behavior is easy to miss because you never write the schema yourself. The return type does it for you. And in [`mcp 2.0.0`, published to PyPI on July 28, 2026](https://pypi.org/project/mcp/), the machinery that reads your annotation moved and got a new name, so it's worth looking at exactly what it produces. Two tools that both "return a dictionary" can come out with completely different schemas depending on how you typed them, and a return value that doesn't match its declared type is rejected on the server before the client sees a byte.

This is a walkthrough of what the official Python SDK actually generates, checked by running it — not by reading the docs.

## What changed in mcp 2.0

`mcp 2.0.0` is a major rework of the SDK. The high-level server class you may know as `FastMCP` — imported for years from `mcp.server.fastmcp` — is gone from that path. In its place is `MCPServer`, exported from `mcp.server.mcpserver`:

```python
from mcp.server.mcpserver import MCPServer   # 2.0
# from mcp.server.fastmcp import FastMCP     # <= 1.x, ModuleNotFoundError on 2.0
```

The decorator-driven ergonomics are the same — `@server.tool()` still turns a plain function into a registered tool. What's underneath is what this article is about: the code that turns your function's *return annotation* into an `outputSchema`.

Structured output itself isn't new to 2.0. It arrived in the [MCP specification dated 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools), which added a `structuredContent` field to tool results and an optional `outputSchema` on tool definitions. The spec's own words: "Structured content is returned as a JSON object in the `structuredContent` field of a result," and, for older clients, "a tool that returns structured content SHOULD also return the serialized JSON in a TextContent block." Clients "SHOULD validate structured results against this schema."

The spec says *what* goes on the wire. The SDK decides *how your Python types become that schema*. Those rules are the interesting part.

## The return type is the schema

Here is the rule the SDK follows, straight from `mcp/server/mcpserver/utilities/func_metadata.py`. Your return annotation falls into one of a few buckets:

- **A `BaseModel`, a `TypedDict`, a dataclass, or any class with type hints** becomes the output schema *directly*. Its fields are the object's fields.
- **`dict[str, X]`** becomes an object with `additionalProperties` typed as `X` — an open-ended map, not wrapped.
- **A primitive (`int`, `str`, `float`, `bool`, `bytes`), `None`, a `list`/`tuple`, a `Union`/`Optional`, or a `dict` with non-string keys** gets *wrapped* in a synthetic model with one field named `result`. JSON Schema has no top-level "just an integer" object shape a tool result can carry, so the SDK boxes it.
- **No return annotation at all** produces no `outputSchema`. The tool is unstructured — text only, exactly like pre-spec tools.

The wrapping is the surprising one. A function typed `-> int` produces a schema titled `addOutput` whose single property is `result`. That's why the `5` becomes `{"result": 5}`. The relevant helper is short and blunt about it:

```python
def _create_wrapped_model(func_name: str, annotation: Any) -> type[BaseModel]:
    """Create a model that wraps a type in a 'result' field.
    This is used for primitive types, generic types like list/dict, etc.
    """
    model_name = f"{func_name}Output"
    return create_model(model_name, result=annotation)
```

## Try It Yourself

You need one dependency and no API key — this is all local schema construction and in-process tool calls. No model is invoked.

```bash
python -m venv venv && source venv/bin/activate
pip install "mcp==2.0.0"
python output_schema_probe.py
```

The probe registers five tools with five different return annotations, then does three things: prints the `outputSchema` the server generated for each, calls two of them to show what lands on the wire, and calls one whose body lies about its return type.

```python
from dataclasses import dataclass
from mcp.server.mcpserver import MCPServer

server = MCPServer("probe")

@server.tool()
def add(a: int, b: int) -> int:        # primitive -> wrapped under "result"
    return a + b

@server.tool()
def prices() -> dict[str, int]:        # dict[str, X] -> open object, NOT wrapped
    return {"apple": 3, "pear": 5}

@dataclass
class Quote:
    symbol: str
    usd: float

@server.tool()
def quote() -> Quote:                  # class with hints -> object, NOT wrapped
    return Quote(symbol="ACME", usd=12.5)

@server.tool()
def legacy():                          # no annotation -> NO outputSchema
    return "whatever"
```

Listing the tools and reading `output_schema` off each one prints exactly what the client would receive at `tools/list`:

```
=== 1. outputSchema generated from each return annotation ===
add      -> title='addOutput'        fields=['result']
prices   -> title='pricesDictOutput' fields=additionalProperties=True
quote    -> title='Quote'            fields=['symbol', 'usd']
note     -> title='noteOutput'       fields=['result']
legacy   -> outputSchema: None (unstructured)
```

Four annotations, four different outcomes. `add` and `note` (an `int` and a `str`) are boxed under `result`. `prices` becomes an open map. `quote` becomes a real object with `symbol` and `usd`. `legacy`, with no annotation, gets nothing.

Now call the tools and look at the actual result payload. Every structured result carries *both* a text `content` block (the backwards-compatibility path the spec asks for) and the `structuredContent`:

```
=== 2. what the server actually puts on the wire ===
add      content(text)='5'                  structuredContent={'result': 5}
prices   content(text)='{\n  "apple": 3,\n  "pear": 5\n}' structuredContent={'apple': 3, 'pear': 5}
```

There it is: `add` returned `5`, and the structured payload is `{'result': 5}`. `prices` returned a dict, and its structured payload is the dict itself — no `result` wrapper, because `dict[str, int]` isn't a primitive.

The third call is the one that changes how you'll write tools. Declare `-> dict[str, int]` and then return a value that violates it:

```python
@server.tool()
def bad() -> dict[str, int]:
    return {"apple": "free"}   # str where the schema promised int

await server.call_tool("bad", {})
```

The server validates the return value against the model it built from your annotation, and refuses:

```
=== 3. a return that violates the declared schema is rejected here ===
ToolError: Error executing tool bad: 1 validation error for DictModel
```

That validation happens in `convert_result`, which calls `output_model.model_validate(result)` before packaging the response. A tool that promises `int` values and produces a string never reaches the client with bad data — it errors at the boundary. Your return annotation is not documentation. It's an enforced contract.

## Why the wrapping actually matters

The `result` wrapper is not cosmetic. A client reading your `-> list[str]` tool has to reach into `structuredContent["result"]` to get the list, because the schema promised an object with a `result` array, not a bare array. If you assume the list arrives at the top level, your client code breaks — not on your machine, where you also wrote the tool and know the shape, but on someone else's, reading only the published schema.

There's a clean way to avoid the surprise: when you want a structured object, return one. Type your tool `-> Quote` or `-> SomeBaseModel` or a `TypedDict`, and the schema is the object you designed, with the field names you chose. Reserve bare primitives and lists for cases where a `result` box is genuinely fine. The SDK will happily wrap them, but now you know that's what "happily wrap" means.

And because the annotation is validated, treat it the way you'd treat a function signature in typed code: make it true. `-> dict[str, int]` is a promise the server will hold you to on every call, in production, with a `ToolError` if you break it. That's a feature — it moves a class of "the model got malformed tool output" bugs from the client's problem to a loud failure at the source — but only if your annotations are honest.

## Key Takeaways

- In `mcp 2.0.0` (July 28, 2026), the high-level server is `MCPServer` from `mcp.server.mcpserver`; the old `mcp.server.fastmcp` import path is gone.
- Your tool's **return annotation** is compiled into its `outputSchema` automatically. You rarely write the schema by hand.
- Primitives, `None`, lists, tuples, unions, and non-string-keyed dicts are **wrapped** in a synthetic model with one `result` field. A `-> int` returning `5` ships as `{"result": 5}`.
- `dict[str, X]` becomes an open `additionalProperties` object; a `BaseModel`, `TypedDict`, dataclass, or hinted class becomes the object schema directly, with your field names.
- No return annotation means **no** `outputSchema` — the tool stays text-only.
- Every structured result also carries a text `content` block for backwards compatibility, per the 2025-06-18 spec.
- The server **validates** the return value against the schema and raises `ToolError` on a mismatch, before the client sees anything. Type your tools honestly.

**Sources:** [mcp on PyPI (2.0.0, Jul 28 2026)](https://pypi.org/project/mcp/); [MCP specification 2025-06-18 — Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools); [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk); and direct inspection of `mcp/server/mcpserver/utilities/func_metadata.py` and `.../tools/base.py` in the installed `mcp==2.0.0` package.
