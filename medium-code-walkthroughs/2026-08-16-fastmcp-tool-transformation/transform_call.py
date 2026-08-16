"""The model calls the transformed tool with 2 args. Does the hidden secret
still reach the underlying function? Real in-memory round-trip."""
import asyncio, json
from fastmcp import FastMCP, Client
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform

mcp = FastMCP("weather")

@mcp.tool
def get_forecast(lat: float, lon: float, appid: str, units: str = "imperial") -> dict:
    """Raw upstream forecast endpoint."""
    return {"lat": lat, "lon": lon, "units": units, "used_key": appid[:4] + "..."}

mcp.add_tool(Tool.from_tool(
    get_forecast,
    name="forecast",
    transform_args={
        "lat":   ArgTransform(name="latitude"),
        "lon":   ArgTransform(name="longitude"),
        "appid": ArgTransform(hide=True, default="sk-demo-abcd-1234"),
        "units": ArgTransform(hide=True, default="metric"),
    },
))

async def main():
    async with Client(mcp) as client:
        # The model only knows two arguments exist.
        result = await client.call_tool("forecast", {"latitude": 48.85, "longitude": 2.35})
        print("model passed:  {latitude: 48.85, longitude: 2.35}")
        print("function saw: ", json.dumps(result.data))

        # It cannot set the secret even if it tries.
        try:
            await client.call_tool("forecast", {"latitude": 0, "longitude": 0,
                                                "appid": "attacker-key"})
        except Exception as e:
            print("inject attempt:", type(e).__name__, "-", str(e).split("\n")[0])

asyncio.run(main())
