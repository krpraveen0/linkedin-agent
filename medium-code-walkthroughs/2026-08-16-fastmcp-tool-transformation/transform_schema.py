"""What schema does a connected client actually see after tool transformation?
Runs a real in-memory FastMCP client<->server round-trip. No API key, no network.
"""
import asyncio, json
from fastmcp import FastMCP, Client
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform

mcp = FastMCP("weather")

# A "third-party" tool you don't control: cryptic params + a secret you must pass.
@mcp.tool
def get_forecast(lat: float, lon: float, appid: str, units: str = "imperial") -> dict:
    """Raw upstream forecast endpoint."""
    return {"lat": lat, "lon": lon, "units": units, "used_key": appid[:4] + "..."}

# Adapt it for the model: rename lat/lon, hide the secret + pin units.
better = Tool.from_tool(
    get_forecast,
    name="forecast",
    description="Get the forecast for a latitude/longitude, in Celsius.",
    transform_args={
        "lat":   ArgTransform(name="latitude"),
        "lon":   ArgTransform(name="longitude"),
        "appid": ArgTransform(hide=True, default="sk-demo-abcd-1234"),
        "units": ArgTransform(hide=True, default="metric"),
    },
)
mcp.add_tool(better)

def params(schema):
    props = list(schema.get("properties", {}))
    req = schema.get("required", [])
    return props, req

async def main():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
        for name in ("get_forecast", "forecast"):
            props, req = params(tools[name].inputSchema)
            print(f"{name:>13} | model sees params: {props}  required: {req}")

asyncio.run(main())
