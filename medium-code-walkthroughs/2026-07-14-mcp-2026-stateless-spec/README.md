# MCP 2026-07-28 stateless spec: cache hints + routing headers

Two things this proves, against a real installed `mcp==2.0.0b1`, not the blog post:

1. **SEP-2549** — a `tools/list` result can carry a `ttlMs`/`cacheScope` freshness
   hint. Set server-wide via `MCPServer(cache_hints={"tools/list": CacheHint(...)})`.
2. **SEP-2243** — every stateless request must send an `Mcp-Method` header that
   matches the JSON-RPC body's `method`, and for name-bearing methods
   (`tools/call`, `prompts/get`, `resources/read`) an `Mcp-Name` header matching
   the body's name/uri param. Mismatches get HTTP 400 with JSON-RPC error code
   `-32020`. No session cookie is used across requests — each call is
   fully self-describing (the "sessions are gone" part of the spec).

## What's in here

- `server.py` — a stateless `MCPServer` with one tool (`get_price`) and a
  `tools/list` cache hint (`ttl_ms=60_000, scope="public"`).
- `client_raw_http.py` — raw `httpx` calls (no SDK `ClientSession`, so the
  header mechanics are visible) against the running server: one valid
  `tools/list` call, one with a missing `Mcp-Method` header, one `tools/call`
  with a mismatched `Mcp-Name` header.
- `requirements.txt` — exact versions from the venv this was run in.

## Prerequisites

- Python 3.12+ (a fresh virtualenv is strongly recommended: `mcp==2.0.0b1` is
  a pre-release and must be pinned exactly — plain `pip install mcp` will
  install the stable v1.28.1 line, which does not implement this spec).

```bash
python3 -m venv venv
source venv/bin/activate
pip install "mcp==2.0.0b1" httpx
```

## Run it

Terminal 1:

```bash
python server.py
# Uvicorn running on http://127.0.0.1:8931
```

Terminal 2:

```bash
python client_raw_http.py
```

## What was actually verified by inspecting the installed package

Confirmed real (via `dir()`/`inspect.signature`/reading site-packages source,
independent of the SDK-betas blog post):

- `mcp.server.CacheHint(ttl_ms: int = 0, scope: Literal["public","private"] = "private")`
  and `mcp.server.Server`/`MCPServer(..., cache_hints=...)` exist and work —
  verified live: the `tools/list` response above came back with
  `"cacheScope":"public","ttlMs":60000` in the JSON-RPC result.
- `mcp.shared.inbound.classify_inbound_request` enforces `Mcp-Method` (always)
  and `Mcp-Name` (for `tools/call`/`prompts/get`/`resources/read`) against the
  request body, and rejects mismatches with JSON-RPC error code `-32020`
  (`mcp_types.jsonrpc.HEADER_MISMATCH`) / HTTP 400 — verified live against the
  running server, not just read from source.
- `MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)` and `CACHEABLE_METHODS` include
  `tools/list`, `resources/read`, `resources/list`, `prompts/list`,
  `resources/templates/list`, `server/discover`.
- The low-level ergonomic/decorator server class in this package is
  `MCPServer` (`mcp.server.MCPServer`), **not** `FastMCP` — `grep -rl "class
  FastMCP"` over the installed package returned nothing, and `fastmcp` is a
  separate PyPI package this demo does not use.

Could **not** confirm — and did not build on:

- The redesigned Tasks lifecycle (`tasks/get`, `tasks/update`, `tasks/cancel`)
  claimed for the new spec. `mcp_types.v2026_07_28` (the module for protocol
  revision `2026-07-28`) has **zero** task-related classes or methods (`grep
  -i task` on its `__init__.py` returns nothing but one comment mentioning an
  extension namespace string `"io.modelcontextprotocol/tasks"`). The
  redesigned Tasks types that do exist in this package (`GetTaskPayloadResult`,
  `Tasks`, `RelatedTaskMetadata`, etc.) all live under
  `mcp_types.v2025_11_25` — the *previous* protocol revision — and
  `mcp.server.extension` only documents a hook for an extension to add
  `tasks/get`-style methods, it doesn't implement the lifecycle itself. This
  is why the demo does not touch Tasks: as of `2.0.0b1`, it is not part of the
  2026-07-28 modern envelope.
