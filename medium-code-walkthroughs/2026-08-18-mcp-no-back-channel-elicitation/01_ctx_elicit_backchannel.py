"""What ctx.elicit() does on a 2026-07-28 connection vs a legacy one."""
import asyncio

from pydantic import BaseModel
import mcp_types as t
from mcp.client import Client
from mcp.server.mcpserver import MCPServer, Context
from mcp.shared.exceptions import NoBackChannelError


class Quantity(BaseModel):
    count: int


server = MCPServer("shop")


@server.tool()
async def order(item: str, ctx: Context) -> str:
    # The pre-2026 way: the tool reaches back to the client mid-call.
    result = await ctx.elicit("How many would you like?", Quantity)
    if result.action == "accept":
        return f"Ordered {result.data.count} x {item}"
    return f"No order ({result.action})"


async def answer(context, params: t.ElicitRequestParams) -> t.ElicitResult:
    return t.ElicitResult(action="accept", content={"count": 3})


def find_nbc(exc: BaseException) -> NoBackChannelError | None:
    # The error is raised server-side and arrives wrapped in nested task groups.
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
    except BaseException as exc:  # noqa: BLE001
        if nbc := find_nbc(exc):
            print(f"raised NoBackChannelError: {nbc}")
        else:
            raise


async def main() -> None:
    await call_on("2026-07-28")
    await call_on("legacy")


asyncio.run(main())
