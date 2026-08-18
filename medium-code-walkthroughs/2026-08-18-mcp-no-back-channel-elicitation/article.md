# My MCP Tool Called ctx.elicit(). On a 2026 Connection, the SDK Raised Before the User Saw It.

I had an MCP tool that asked the user a follow-up question mid-call. It placed an order, and if the quantity was missing it called `ctx.elicit()` to ask "how many?" before finishing. That worked for a year. Then I upgraded the Python SDK to 2.0, my client negotiated the `2026-07-28` protocol, and the same tool blew up with an error I'd never seen:

```
NoBackChannelError: Cannot send 'elicitation/create': this transport context
has no back-channel for server-initiated requests.
```

The user never saw the question. The SDK refused to deliver it. This isn't a bug in my tool — it's the single largest behavioral change in the [2026-07-28 MCP specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/), published on July 28, 2026, and it will break any server that asks the client for something in the middle of handling a request.

Here is exactly what changed, verified against the installed `mcp` 2.0.0 package rather than the announcement, and the small rewrite that makes one tool work on both old and new connections.

## The back-channel is gone

In every MCP version before this one, a server could reach *back* to the client while it was processing a request. Three features relied on it:

- `elicitation/create` — ask the user a structured question.
- `sampling/createMessage` — ask the client's LLM to generate something.
- `roots/list` — ask the client which directories it exposes.

All three were **server-initiated requests**: the server opened a request to the client mid-call and blocked, waiting for the answer to come back over a live, two-way stream. That only works if there is a held-open connection and both sides are the same two processes for the whole exchange.

The 2026-07-28 spec deleted that pattern. Per the official spec blog, the new Multi Round-Trip Requests model (MRTR, [SEP-2322](https://blog.modelcontextprotocol.io/posts/2026-07-28/)) "replaces the server-initiated `elicitation/create`, `sampling/createMessage`, and `roots/list` requests that previously required a held-open stream." Instead of reaching back, "the server returns `resultType: "input_required"` along with the requests it needs answered, and the client retries the original call with the answers attached in `inputResponses`."

The motivation is statelessness. The same release converted MCP into a request/response protocol that can run serverless and load-balanced, where no two round trips are guaranteed to hit the same worker. A server that blocks mid-call waiting for the client to answer cannot survive that. So the channel it used to block on simply doesn't exist anymore.

You can see the two worlds in the SDK's own version constants:

```
HANDSHAKE_PROTOCOL_VERSIONS: ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')
MODERN_PROTOCOL_VERSIONS:    ('2026-07-28',)
```

The four "handshake" versions carry the back-channel. The one "modern" version does not.

## Reproducing the break

Here is a tool that uses the old `ctx.elicit()`, run against both a modern connection and a legacy one. The high-level `Client` lets you pin the protocol version with `mode`, so I can trigger both paths from one script. (`answer` is the client-side callback that would supply the user's response; `find_nbc` is only there because the error arrives wrapped in nested task groups.)

```python
@server.tool()
async def order(item: str, ctx: Context) -> str:
    # The pre-2026 way: the tool reaches back to the client mid-call.
    result = await ctx.elicit("How many would you like?", Quantity)
    if result.action == "accept":
        return f"Ordered {result.data.count} x {item}"
    return f"No order ({result.action})"

def find_nbc(exc: BaseException) -> NoBackChannelError | None:
    if isinstance(exc, NoBackChannelError):
        return exc
    for sub in getattr(exc, "exceptions", []):
        if found := find_nbc(sub):
            return found
    return None

async def call_on(mode: str) -> None:
    print(f"\n--- protocol {mode} ---")
    try:
        async with Client(server, mode=mode, elicitation_callback=answer) as client:
            result = await client.call_tool("order", {"item": "widget"})
            print("tool result:", result.content[0].text)
    except BaseException as exc:
        if nbc := find_nbc(exc):
            print(f"raised NoBackChannelError: {nbc}")
        else:
            raise
```

Calling `call_on("2026-07-28")` and then `call_on("legacy")` produces (full imports and the `answer` callback are in the [walkthrough repo](PR_LINK_PLACEHOLDER)):

```
--- protocol 2026-07-28 ---
raised NoBackChannelError: Cannot send 'elicitation/create': this transport context has no back-channel for server-initiated requests.

--- protocol legacy ---
tool result: Ordered 3 x widget
```

Same tool, same client callback, same question. On the legacy handshake it works. On a 2026-07-28 connection the SDK raises the moment `ctx.elicit()` tries to send, before anything reaches the user. I verified where this comes from: the server-side `send_raw_request` checks whether its request-scoped channel can send, and raises `NoBackChannelError` when it can't. It is a hard failure, not a fallback.

One detail worth noting for error handling: this surfaces as a raised exception propagating out through the async task group, not as a normal `isError` tool result. If your framework wraps tool bodies expecting clean error results, a stray `ctx.elicit()` can escape that handling entirely.

## The fix: ask by returning, not by reaching back

The SDK's answer is to stop calling `ctx.elicit()` yourself and instead declare the need as a **resolver**. You annotate a tool parameter with `Resolve(fn)`, where `fn` returns an `Elicit(...)` marker describing the question. The framework runs the resolver before your tool body and injects the answer. On a 2025 connection it sends a live request; on a 2026 connection it batches the question into an `input_required` result and resumes when the client retries. Your tool body is identical either way.

```python
from typing import Annotated
from pydantic import BaseModel
import mcp_types as t
from mcp.client import Client
from mcp.server.mcpserver import MCPServer, Resolve, Elicit

class Quantity(BaseModel):
    count: int

server = MCPServer("shop")

def ask_quantity() -> Elicit[Quantity]:
    # A resolver: instead of returning a value, it asks the client for one.
    return Elicit("How many would you like to order?", Quantity)

@server.tool()
def order(item: str, qty: Annotated[Quantity, Resolve(ask_quantity)]) -> str:
    return f"Ordered {qty.count} x {item}"

async def answer(context, params: t.ElicitRequestParams) -> t.ElicitResult:
    print(f"   [client] server asked: {params.message!r}")
    print(f"   [client] requested_schema: {params.requested_schema['properties']}")
    return t.ElicitResult(action="accept", content={"count": 3})

async def main() -> None:
    async with Client(server, mode="2026-07-28", elicitation_callback=answer) as client:
        print(f"negotiated protocol version: {client.protocol_version}")
        result = await client.call_tool("order", {"item": "widget"})
        print("tool result:", result.content[0].text)
```

Run against the modern connection:

```
negotiated protocol version: 2026-07-28
   [client] server asked: 'How many would you like to order?'
   [client] requested_schema: {'count': {'title': 'Count', 'type': 'integer'}}
tool result: Ordered 3 x widget
```

The elicitation went through on the exact connection that raised `NoBackChannelError` a moment ago. Note what the client did: it received an `input_required` result, invoked the same `elicitation_callback`, and retried the tool call with the answer attached — and the high-level `Client` drove that whole loop for me. The tool body never mentions elicitation, retries, or protocol versions. It just declares that `qty` comes from asking the user.

Two things the SDK enforces around this that are easy to miss:

- **The question is asked once.** Resolver bodies can re-run on each retry round, but only outcomes that were actually *asked* are carried forward in the request state, so the client isn't re-prompted every round.
- **Decline and cancel still exist.** With `Annotated[Quantity, Resolve(...)]` you get the unwrapped value and a decline or cancel aborts the whole call. If you want to handle those cases yourself, annotate the parameter as `Annotated[ElicitationResult[Quantity], Resolve(...)]` and branch on `accept` / `decline` / `cancel`.

And a constraint that predates this change but still bites: elicitation schemas may only use primitive types. The `requested_schema` in the output above is a flat object of scalar properties. Nesting a model inside your elicitation schema is not allowed.

## Try It Yourself

Everything above runs locally with no API key and no model. You need Python 3.11+ and the `mcp` 2.0 package:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "mcp"          # installs mcp 2.0.0 (2.x by default)
python3 01_ctx_elicit_backchannel.py
python3 02_resolve_elicit.py
```

The first script prints the `NoBackChannelError` on the modern connection and the working result on the legacy one. The second prints the resolver-based elicitation succeeding on the modern connection. Both outputs are the real captured stdout shown above, produced on `mcp` 2.0.0 with `mcp-types` 2.0.0 and `pydantic` 2.13.4 under CPython 3.11.15.

If you maintain an MCP server, the migration test is simple: grep your tool bodies for `ctx.elicit`, `ctx.session.create_message`, and `list_roots`. Every hit is a tool that will raise on a 2026-07-28 client until you move the request into a resolver.

## Key Takeaways

- The 2026-07-28 MCP spec removed server-initiated requests. `elicitation/create`, `sampling/createMessage`, and `roots/list` no longer exist as mid-call callbacks.
- In the `mcp` 2.0 Python SDK, calling `ctx.elicit()` on a `2026-07-28` connection raises `NoBackChannelError` before the user ever sees the prompt. The same call still works on legacy handshake connections.
- The replacement is Multi Round-Trip Requests (MRTR, SEP-2322): the server returns `input_required`, and the client retries with the answers attached. It exists because the spec went stateless.
- In the SDK you express this by annotating a tool parameter with `Resolve(fn)` and returning an `Elicit(...)` marker. One tool body then works on both old and new connections, and the high-level `Client` drives the retry loop for you.
- Handle `decline` and `cancel` explicitly with `Annotated[ElicitationResult[T], Resolve(...)]`, and remember elicitation schemas are primitives-only.

*Sources: [The 2026-07-28 Specification — Model Context Protocol Blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/) (July 28, 2026); [MCP Python SDK v2 — What's New](https://py.sdk.modelcontextprotocol.io/whats-new/); and direct inspection of the installed `mcp` 2.0.0 package source (`mcp/shared/exceptions.py`, `mcp/server/mcpserver/resolve.py`, `mcp/client/client.py`). Code walkthrough (auto-generated by the daily-medium-article cloud routine): PR_LINK_PLACEHOLDER*
