"""Probe how mcp 2.0 turns a tool's return annotation into an outputSchema.

Run: python output_schema_probe.py
Requires: mcp==2.0.0  (pip install "mcp==2.0.0")
"""
import asyncio
import json
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("probe")


@server.tool()
def add(a: int, b: int) -> int:          # primitive -> wrapped under "result"
    return a + b


@server.tool()
def prices() -> dict[str, int]:          # dict[str, X] -> object, NOT wrapped
    return {"apple": 3, "pear": 5}


@dataclass
class Quote:
    symbol: str
    usd: float


@server.tool()
def quote() -> Quote:                     # class with type hints -> object, NOT wrapped
    return Quote(symbol="ACME", usd=12.5)


@server.tool()
def note() -> str:                        # str stays a primitive -> wrapped
    return "hello"


@server.tool()
def legacy():                             # no annotation -> NO outputSchema at all
    return "whatever"


async def main() -> None:
    print("=== 1. outputSchema generated from each return annotation ===")
    for t in await server.list_tools():
        s = t.output_schema
        if s is None:
            print(f"{t.name:8} -> outputSchema: None (unstructured)")
        else:
            keys = list(s.get("properties", {})) or f"additionalProperties={'additionalProperties' in s}"
            print(f"{t.name:8} -> title={s['title']!r:18} fields={keys}")

    print("\n=== 2. what the server actually puts on the wire ===")
    for name in ("add", "prices"):
        res = await server.call_tool(name, {"a": 2, "b": 3} if name == "add" else {})
        text = res.content[0].text
        print(f"{name:8} content(text)={text!r:20} structuredContent={res.structured_content}")

    print("\n=== 3. a return that violates the declared schema is rejected here ===")

    @server.tool()
    def bad() -> dict[str, int]:
        return {"apple": "free"}          # str where the schema promised int

    try:
        await server.call_tool("bad", {})
    except ToolError as e:
        first_line = str(e).splitlines()[0]
        print("ToolError:", first_line)


asyncio.run(main())
