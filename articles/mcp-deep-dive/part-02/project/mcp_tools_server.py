#!/usr/bin/env python3
"""A minimal MCP server exposing two tools over the STDIO transport.

Follows the wire shapes from the MCP spec (JSON-RPC 2.0, newline-delimited
messages on stdin/stdout, https://modelcontextprotocol.io/introduction):
  - initialize            -> capability handshake
  - tools/list             -> advertise available tools + JSON Schemas
  - tools/call              -> execute a tool by name and return its result

The two tools model a small e-commerce support agent: checking an order's
shipping status and converting a price between currencies. Both are pure
functions with no network/DB dependency so the whole demo runs offline.
"""
import json
import sys

TOOLS = [
    {
        "name": "get_order_status",
        "description": "Look up the shipping status for a customer order.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "convert_currency",
        "description": "Convert an amount from one currency to another.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string"},
                "to_currency": {"type": "string"},
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    },
]

# In-memory fixtures standing in for a real order-management DB / FX rate feed.
_ORDERS = {
    "A1001": {"status": "shipped", "carrier": "UPS", "eta_days": 2},
    "A1002": {"status": "processing", "carrier": None, "eta_days": None},
}
_FX_RATES_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "INR": 0.012}


def _call_tool(name: str, arguments: dict) -> dict:
    if name == "get_order_status":
        order = _ORDERS.get(arguments["order_id"])
        if order is None:
            return {"error": f"unknown order_id {arguments['order_id']!r}"}
        return order
    if name == "convert_currency":
        amount = arguments["amount"]
        from_ccy = arguments["from_currency"].upper()
        to_ccy = arguments["to_currency"].upper()
        usd = amount * _FX_RATES_TO_USD[from_ccy]
        converted = usd / _FX_RATES_TO_USD[to_ccy]
        return {"converted_amount": round(converted, 2), "to_currency": to_ccy}
    return {"error": f"unknown tool {name!r}"}


def _handle(message: dict) -> dict:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-11-25", "serverInfo": {"name": "support-tools", "version": "0.1.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params", {})
        result = _call_tool(params["name"], params.get("arguments", {}))
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message = json.loads(line)
        response = _handle(message)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
