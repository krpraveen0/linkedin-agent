"""Transformation isn't only renaming: transform_fn wraps the upstream tool in
your own logic, then forward() calls the original with mapped arguments."""
import asyncio, json
from fastmcp import FastMCP, Client
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform, forward

mcp = FastMCP("weather")

@mcp.tool
def get_forecast(lat: float, lon: float, appid: str, units: str = "imperial") -> dict:
    return {"lat": lat, "lon": lon, "units": units, "used_key": appid[:4] + "..."}

async def guarded(latitude: float, longitude: float) -> dict:
    if not (-90 <= latitude <= 90):
        raise ValueError(f"latitude {latitude} out of range")
    # forward() maps to the parent tool's original names + injects hidden args.
    return await forward(latitude=latitude, longitude=longitude)

mcp.add_tool(Tool.from_tool(
    get_forecast, name="forecast",
    transform_args={
        "lat":   ArgTransform(name="latitude"),
        "lon":   ArgTransform(name="longitude"),
        "appid": ArgTransform(hide=True, default="sk-demo-abcd-1234"),
        "units": ArgTransform(hide=True, default="metric"),
    },
    transform_fn=guarded,
))

async def main():
    async with Client(mcp) as client:
        ok = await client.call_tool("forecast", {"latitude": 48.85, "longitude": 2.35})
        print("valid   ->", json.dumps(ok.data))
        try:
            await client.call_tool("forecast", {"latitude": 999, "longitude": 2.35})
        except Exception as e:
            print("bad lat ->", type(e).__name__, "-", str(e).split("\n")[0])

asyncio.run(main())
