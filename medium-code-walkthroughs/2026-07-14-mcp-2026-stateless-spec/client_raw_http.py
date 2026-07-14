"""Raw HTTP client (no SDK ClientSession) against the running stateless
server, to make the 2026-07-28 per-request envelope + Mcp-Method/Mcp-Name
header requirement (SEP-2243) visible on the wire.

Every field/header name here was read directly from the installed
mcp==2.0.0b1 source (mcp.shared.inbound, mcp_types), not guessed from docs.
"""

import httpx

URL = "http://127.0.0.1:8931/mcp"

# Reserved envelope keys a stateless request's params._meta must carry
# (mcp_types.PROTOCOL_VERSION_META_KEY / CLIENT_INFO_META_KEY / CLIENT_CAPABILITIES_META_KEY).
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "raw-http-demo", "version": "0.1.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}

COMMON_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
    "mcp-protocol-version": "2026-07-28",
}


def call_tools_list_with_headers():
    """Valid request: Mcp-Method matches body.method. tools/list is not in
    NAME_BEARING_METHODS, so no Mcp-Name is required for it."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {"_meta": META},
    }
    headers = {**COMMON_HEADERS, "mcp-method": "tools/list"}
    return httpx.post(URL, json=body, headers=headers, timeout=10)


def call_tools_list_missing_header():
    """Invalid request: Mcp-Method header omitted entirely."""
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {"_meta": META},
    }
    return httpx.post(URL, json=body, headers=COMMON_HEADERS, timeout=10)


def call_tools_call_name_mismatch():
    """Invalid request: Mcp-Name header present but doesn't match the body's
    tool name -> tools/call is in NAME_BEARING_METHODS ('name' key)."""
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"_meta": META, "name": "get_price", "arguments": {"sku": "widget-1"}},
    }
    headers = {**COMMON_HEADERS, "mcp-method": "tools/call", "mcp-name": "wrong_tool_name"}
    return httpx.post(URL, json=body, headers=headers, timeout=10)


if __name__ == "__main__":
    for label, fn in [
        ("1) tools/list, correct Mcp-Method header", call_tools_list_with_headers),
        ("2) tools/list, Mcp-Method header MISSING", call_tools_list_missing_header),
        ("3) tools/call, Mcp-Name header MISMATCHED", call_tools_call_name_mismatch),
    ]:
        print(f"\n=== {label} ===")
        resp = fn()
        print("HTTP status:", resp.status_code)
        print("body:", resp.text[:800])
