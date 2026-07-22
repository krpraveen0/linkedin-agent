"""Demonstrates MCP's two-tier error model for tools/call (SEP-1303).

Unknown method / unknown tool -> JSON-RPC Protocol Error (never reaches the
model's context -- the MCP client handles it).

Bad tool *arguments* (malformed or past-dated departureDate) -> Tool
Execution Error, a normal JSON-RPC result with isError: true. This is the
only error shape the calling model actually sees, so it's the only one
that lets the model read the reason and retry with a corrected argument
instead of repeating the same invalid call.

Standard library only -- no dependencies to install.
"""
import json
import re
import sys
from datetime import datetime

TOOLS = [
    {
        "name": "book_flight",
        "description": "Book a flight for a future departure date.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "departureDate": {
                    "type": "string",
                    "description": "Departure date in dd/mm/yyyy format",
                }
            },
            "required": ["departureDate"],
        },
    }
]

DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _protocol_error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_result(msg_id, text, is_error):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
    }


def _validate_departure_date(raw):
    """Return an error message string, or None if raw is a valid future date."""
    match = DATE_RE.match(raw)
    if not match:
        return f"date must be in dd/mm/yyyy format, got {raw!r}"
    day, month, year = (int(g) for g in match.groups())
    try:
        parsed = datetime(year, month, day)
    except ValueError as exc:
        return f"{raw!r} is not a real calendar date: {exc}"
    if parsed.date() < datetime.now().date():
        return (
            f"departureDate must be in the future; got {raw}, "
            f"current date is {datetime.now():%d/%m/%Y}"
        )
    return None


def handle_request(message):
    method = message.get("method")
    msg_id = message.get("id")

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method != "tools/call":
        # Unknown method: the client asked for an operation this server
        # doesn't implement at all -- a Protocol Error per the spec's
        # "Unknown tools" / "Server errors" category.
        return _protocol_error(msg_id, -32601, f"method not found: {method}")

    params = message.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    known_tools = {t["name"] for t in TOOLS}
    if tool_name not in known_tools:
        # Unknown tool name: same category as an unknown method.
        return _protocol_error(msg_id, -32602, f"unknown tool: {tool_name}")

    departure_date_raw = arguments.get("departureDate")
    if not isinstance(departure_date_raw, str):
        return _tool_result(
            msg_id,
            "departureDate is required and must be a string in dd/mm/yyyy format",
            is_error=True,
        )

    error = _validate_departure_date(departure_date_raw)
    if error:
        # Invalid *argument value* -- per SEP-1303 this is a Tool
        # Execution Error, not a Protocol Error, so the message reaches
        # the model's context and it can retry with a corrected date.
        return _tool_result(msg_id, error, is_error=True)

    return _tool_result(msg_id, f"Flight booked for {departure_date_raw}.", is_error=False)


def main():
    scenarios = [
        (
            "unknown tool -> Protocol Error",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "cancel_flight", "arguments": {}}},
            lambda r: "error" in r and r["error"]["code"] == -32602,
        ),
        (
            "past-dated argument -> Tool Execution Error (isError: true)",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "book_flight", "arguments": {"departureDate": "12/12/2024"}}},
            lambda r: r.get("result", {}).get("isError") is True,
        ),
        (
            "valid future date -> normal tool result (isError: false)",
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "book_flight", "arguments": {"departureDate": "12/12/2099"}}},
            lambda r: r.get("result", {}).get("isError") is False,
        ),
    ]

    all_passed = True
    for label, message, check in scenarios:
        response = handle_request(message)
        passed = check(response)
        all_passed = all_passed and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {label}")
        print(f"  request:  {json.dumps(message)}")
        print(f"  response: {json.dumps(response)}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
