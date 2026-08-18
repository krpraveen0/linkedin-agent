# MCP 2.0: `ctx.elicit()` and the removed back-channel

Code for the daily Medium article **"My MCP Tool Called ctx.elicit(). On a 2026 Connection, the SDK Raised Before the User Saw It."** (2026-08-18).

The 2026-07-28 MCP spec removed server-initiated requests (`elicitation/create`, `sampling/createMessage`, `roots/list`). In the `mcp` 2.0 Python SDK, calling `ctx.elicit()` on a `2026-07-28` connection raises `NoBackChannelError`. The replacement is the `Resolve(Elicit[...])` pattern (Multi Round-Trip Requests / MRTR), which works on both legacy and modern connections.

Both examples run fully locally — no API key, no model, no network.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "mcp"          # installs mcp 2.0.0 (2.x by default)
```

Verified with: `mcp` 2.0.0, `mcp-types` 2.0.0, `pydantic` 2.13.4, CPython 3.11.15.

## `01_ctx_elicit_backchannel.py` — the break

Runs a tool that calls `ctx.elicit()` against a `2026-07-28` connection and a legacy one.

```bash
python3 01_ctx_elicit_backchannel.py
```

Real captured output:

```
--- protocol 2026-07-28 ---
raised NoBackChannelError: Cannot send 'elicitation/create': this transport context has no back-channel for server-initiated requests.

--- protocol legacy ---
tool result: Ordered 3 x widget
```

## `02_resolve_elicit.py` — the fix

Runs the same elicitation as a `Resolve(Elicit[...])` resolver against a `2026-07-28` connection. The high-level `Client` drives the input-required retry loop.

```bash
python3 02_resolve_elicit.py
```

Real captured output:

```
negotiated protocol version: 2026-07-28
   [client] server asked: 'How many would you like to order?'
   [client] requested_schema: {'count': {'title': 'Count', 'type': 'integer'}}
tool result: Ordered 3 x widget
```

## Files

- `01_ctx_elicit_backchannel.py` — `ctx.elicit()` on modern vs legacy connections
- `02_resolve_elicit.py` — the `Resolve`/`Elicit` MRTR pattern
- `article.md` — the full article
- `figure1-backchannel-vs-mrtr.svg` — old back-channel flow vs new return-and-retry flow
- `figure2-sdk-paths.svg` — what each SDK code path does on a 2026-07-28 connection

## Sources

- [The 2026-07-28 Specification — Model Context Protocol Blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/) (July 28, 2026)
- [MCP Python SDK v2 — What's New](https://py.sdk.modelcontextprotocol.io/whats-new/)
- Direct inspection of the installed `mcp` 2.0.0 package source
