"""New elicitation on a back-channel-free 2026-07-28 connection: Resolve + Elicit."""
import asyncio
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
    # The client side answers the elicitation. Here we just hard-code "3".
    print(f"   [client] server asked: {params.message!r}")
    print(f"   [client] requested_schema: {params.requested_schema['properties']}")
    return t.ElicitResult(action="accept", content={"count": 3})


async def main() -> None:
    async with Client(server, mode="2026-07-28", elicitation_callback=answer) as client:
        print(f"negotiated protocol version: {client.protocol_version}")
        result = await client.call_tool("order", {"item": "widget"})
        print("tool result:", result.content[0].text)


asyncio.run(main())
