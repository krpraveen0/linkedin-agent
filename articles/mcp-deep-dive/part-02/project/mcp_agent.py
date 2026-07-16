#!/usr/bin/env python3
"""Agent loop tying the MCP tools server to a tool-calling model.

Run with `python3 mcp_agent.py` (see README.md). It:
  1. Launches mcp_tools_server.py as a subprocess (the MCP STDIO transport).
  2. Sends `initialize` then `tools/list` to discover what the server offers.
  3. For each sample user message, asks the tool-calling model (see
     tool_calling_model.py) whether a tool applies, sends `tools/call` if so,
     and prints the JSON-RPC exchange plus a synthesized final answer.
"""
import json
import subprocess
import sys
from pathlib import Path

from tool_calling_model import decide_tool_call

SAMPLE_MESSAGES = [
    "What's the status of order A1001?",
    "Can you convert 100 USD to EUR?",
    "What's the weather like today?",  # no matching tool -> should fall through
]


class McpClient:
    def __init__(self, server_path: Path):
        self.proc = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 1

    def request(self, method: str, params: dict | None = None) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)


def main() -> None:
    server_path = Path(__file__).parent / "mcp_tools_server.py"
    client = McpClient(server_path)

    init_response = client.request("initialize")
    print(f"[initialize] -> {json.dumps(init_response)}")

    tools_response = client.request("tools/list")
    tools = tools_response["result"]["tools"]
    print(f"[tools/list] -> {len(tools)} tools: {[t['name'] for t in tools]}")
    print()

    for message in SAMPLE_MESSAGES:
        print(f"User: {message}")
        call = decide_tool_call(message, tools)
        if call is None:
            print("Agent: no tool matched this message; would fall back to a direct model answer.")
            print()
            continue

        print(f"  tool-calling model decided -> {json.dumps(call)}")
        response = client.request("tools/call", {"name": call["name"], "arguments": call["arguments"]})
        print(f"  [tools/call] -> {json.dumps(response)}")

        result = response["result"]
        if call["name"] == "get_order_status":
            if "error" in result:
                print(f"Agent: {result['error']}")
            else:
                print(f"Agent: your order is {result['status']} via {result['carrier']}, ETA {result['eta_days']} day(s).")
        elif call["name"] == "convert_currency":
            print(f"Agent: that's {result['converted_amount']} {result['to_currency']}.")
        print()

    client.close()


if __name__ == "__main__":
    main()
