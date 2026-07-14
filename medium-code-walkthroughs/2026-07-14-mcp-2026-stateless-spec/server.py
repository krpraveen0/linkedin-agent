"""Minimal MCP server on the 2026-07-28 stateless spec, built against the
real mcp==2.0.0b1 API (verified via inspect.signature / dir(), not the blog post).

Demonstrates SEP-2549: a `tools/list` response carrying a `ttlMs`/`cacheScope`
freshness hint, attached server-wide via `MCPServer(cache_hints=...)`.
"""

from mcp.server import CacheHint, MCPServer

# `cache_hints` maps a CACHEABLE_METHOD name -> CacheHint(ttl_ms, scope).
# CacheHint python fields are ttl_ms/scope; on the wire (SEP-2549) these
# serialize as ttlMs/cacheScope on the JSON-RPC result.
server = MCPServer(
    "pricing-tool-server",
    cache_hints={
        "tools/list": CacheHint(ttl_ms=60_000, scope="public"),
    },
)


@server.tool()
def get_price(sku: str) -> str:
    """Look up the current price for a SKU."""
    catalog = {"widget-1": "$9.99", "widget-2": "$19.99"}
    return catalog.get(sku, "unknown SKU")


if __name__ == "__main__":
    # stateless_http=True: no session cookie/sticky routing - every request
    # is self-describing, per the 2026-07-28 spec's removal of sticky sessions.
    import asyncio

    asyncio.run(
        server.run_streamable_http_async(
            host="127.0.0.1",
            port=8931,
            stateless_http=True,
        )
    )
