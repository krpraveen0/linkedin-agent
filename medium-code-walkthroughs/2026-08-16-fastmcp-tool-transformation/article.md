# I Handed My Agent a Tool With an API-Key Argument. FastMCP Hid It From the Model Before It Could Ask.

Half the tools I want to give an agent were not written for an agent. They are ordinary functions and third-party MCP servers with parameter names like `q`, a required `appid` that is really a secret, and a `units` flag I never want the model to touch. Wire one of those into an LLM unchanged and the model sees the whole mess: it can invent an API key, flip a unit setting, or freeze on a cryptic argument it has no way to fill.

FastMCP's tool transformation feature is built for exactly this. It lets you wrap an existing tool and change the schema the model receives (rename arguments, hide some entirely, pin others to a constant) without editing the original function. I installed the current release and ran a real client-server round-trip to see what the model actually gets after a transform. The secret argument disappears from the model's view, and the model cannot set it even if it tries.

## Why this shows up now

Tool transformation first shipped in the FastMCP 2.x line, but it is not a legacy feature sitting still. The current release line is 3.x: `fastmcp` 3.4.7 shipped on [August 10, 2026](https://pypi.org/project/fastmcp/), and the [changelog](https://github.com/jlowin/fastmcp/blob/main/docs/changelog.mdx) shows transformation getting active maintenance through 2026 — v3.2.4 (2026-04-14) fixed a transformed-tool crash and a schema-mutation bug, and v3.3.0 (2026-05-15) fixed how `ArgTransform` hoists JSON Schema `$defs` to the schema root. The FastMCP 4 beta, dated 2026-07-28, is a migration to the new [2026-07-28 MCP specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/).

The reason transformation matters more in 2026 than it did a year ago is the pile of MCP servers you did not write. When most of your tools are your own functions, you shape the signature at the source. When they arrive from someone else's server, the signature is fixed and transformation is the seam where you make it agent-shaped.

## What a transform actually changes

The API is small. `Tool.from_tool(parent, ...)` returns a new `TransformedTool`, and you describe per-argument changes with `ArgTransform`. The behavior I care about comes straight from the installed package's own docstring for `ArgTransform` (fastmcp 3.4.7):

- `name`: rename the argument.
- `default`: supply a default, which makes the argument optional.
- `hide=True`: "hide this argument from clients but pass a constant value to parent."
- `required=True`: make an optional argument required.

That third one is the interesting case. Hiding is not cosmetic. The argument leaves the schema the client sees, and FastMCP supplies a fixed value to the underlying function on every call. Combine `hide=True` with `default=...` and you have a way to bind a secret or a policy constant server-side, out of the model's reach.

Everything below runs with no API key and no network. FastMCP ships an in-memory client that talks to a server object directly, so a `list_tools` / `call_tool` round-trip is a genuine protocol exchange you can run on a laptop.

## Try It Yourself

### Setup

```bash
python -m venv venv && source venv/bin/activate
pip install "fastmcp==3.4.7"    # pulls mcp 1.29.0, pydantic 2.13.4
```

Verified environment: Python 3.11.15, `fastmcp==3.4.7`, `mcp==1.29.0`, `pydantic==2.13.4`.

### 1. The schema the model sees, before and after

Here is a stand-in for a tool you do not control: a forecast endpoint with a latitude and longitude named `lat`/`lon`, a required `appid` secret, and a `units` flag. We transform it into a clean `forecast` tool, then ask a connected client what each one looks like.

```python
import asyncio
from fastmcp import FastMCP, Client
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform

mcp = FastMCP("weather")

@mcp.tool
def get_forecast(lat: float, lon: float, appid: str, units: str = "imperial") -> dict:
    """Raw upstream forecast endpoint."""
    return {"lat": lat, "lon": lon, "units": units, "used_key": appid[:4] + "..."}

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

async def main():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
        for name in ("get_forecast", "forecast"):
            s = tools[name].inputSchema
            print(f"{name:>13} | model sees params: {list(s.get('properties', {}))}"
                  f"  required: {s.get('required', [])}")

asyncio.run(main())
```

Real output:

```
 get_forecast | model sees params: ['lat', 'lon', 'appid', 'units']  required: ['lat', 'lon', 'appid']
     forecast | model sees params: ['latitude', 'longitude']  required: ['latitude', 'longitude']
```

The raw tool advertises four parameters, and `appid` — the secret — is in the required list. A model calling it is expected to produce an API key. The transformed tool advertises two parameters, both clearly named. The secret and the units flag are gone from the model's view entirely.

### 2. The call: hidden values get injected, and the model can't override them

A schema change is only half the story. When the model calls the transformed tool with its two visible arguments, does the underlying function still get the secret? And what happens if the model tries to pass `appid` anyway?

```python
async def main():
    async with Client(mcp) as client:
        result = await client.call_tool("forecast", {"latitude": 48.85, "longitude": 2.35})
        print("model passed:  {latitude: 48.85, longitude: 2.35}")
        print("function saw: ", json.dumps(result.data))

        try:
            await client.call_tool("forecast", {"latitude": 0, "longitude": 0,
                                                "appid": "attacker-key"})
        except Exception as e:
            print("inject attempt:", type(e).__name__, "-", str(e).split("\n")[0])

asyncio.run(main())
```

Real output (stdout; FastMCP also logs a traceback to stderr for the rejected call):

```
model passed:  {latitude: 48.85, longitude: 2.35}
function saw:  {"lat": 48.85, "lon": 2.35, "units": "metric", "used_key": "sk-d..."}
inject attempt: ToolError - Error calling tool 'forecast': Got unexpected keyword argument(s): appid
```

Two things happened. The function received `units='metric'` and the hidden key (`used_key` shows `sk-d...`, the injected `sk-demo-...`), even though the caller never sent either. And the attempt to smuggle in `appid` was rejected with `Got unexpected keyword argument(s): appid`, because a hidden argument is not part of the transformed tool's schema — it is not an input the caller is allowed to name. The binding is enforced on the server, not suggested in a prompt.

### 3. Transformation can run your own logic

Hiding and renaming cover the common cases, but you can also pass a `transform_fn` — your own async function that runs first and calls the parent through `forward()`. Per the installed `forward` docstring, it maps your transformed argument names back to the parent's names and applies the same injection. That is the place to add validation the upstream tool lacks.

```python
from fastmcp.tools.tool_transform import forward

async def guarded(latitude: float, longitude: float) -> dict:
    if not (-90 <= latitude <= 90):
        raise ValueError(f"latitude {latitude} out of range")
    return await forward(latitude=latitude, longitude=longitude)

# ...Tool.from_tool(get_forecast, name="forecast", transform_args={...}, transform_fn=guarded)
```

Real output:

```
valid   -> {"lat": 48.85, "lon": 2.35, "units": "metric", "used_key": "sk-d..."}
bad lat -> ToolError - Error calling tool 'forecast': latitude 999 out of range
```

The guard runs before the upstream call. A latitude of 999 never reaches the forecast function, and the valid call still forwards with the hidden units and key injected.

## Where this fits, and where it doesn't

The clearest win is wrapping tools you did not write. Point FastMCP at a third-party MCP server, transform its tools into names and shapes your model handles well, and pin the arguments that should be operator policy rather than model choice. The secret-injection pattern is the sharpest edge: an argument the model literally cannot see is an argument it cannot hallucinate, leak into a log, or be talked into changing by a prompt injection in a tool result.

A few limits are worth stating plainly. Hiding an argument is server-side enforcement of *who may set it*, not a general security boundary — the constant you inject still lives in your process, and the upstream tool still runs with real credentials, so ordinary secret-handling still applies. Transformation changes the interface, not the trust level of the code behind it. And because a transform is a real object with its own schema, keep an eye on the changelog: the 2026 fixes to `$defs` handling and schema mutation are a reminder that transformed schemas involving nested Pydantic models have had rough edges, so inspect the generated `inputSchema` for anything complex, exactly as we did above.

None of this requires a running model to verify. The schema a client receives and the arguments the function observes are both inspectable locally, which makes tool transformation one of the few agent-plumbing features you can unit-test with certainty before a single token is spent.

## Key Takeaways

- FastMCP tool transformation (`Tool.from_tool` + `ArgTransform`) rewrites the schema a client sees without editing the original tool — confirmed against `fastmcp` 3.4.7, released [2026-08-10](https://pypi.org/project/fastmcp/).
- `ArgTransform(hide=True, default=...)` removes an argument from the model's view and injects a constant server-side; in a live round-trip the model could not set the hidden `appid`, getting `Got unexpected keyword argument(s): appid`.
- `transform_fn` plus `forward()` lets you add validation or other logic around a tool you do not control, with hidden arguments still injected on the forwarded call.
- It is testable offline: FastMCP's in-memory client gives you a real `list_tools`/`call_tool` exchange with no API key and no network.
- Transformation reshapes a tool's interface without hardening the code behind it; hidden arguments govern who may set an input, and careful secret-handling still applies to the value you inject.

## Sources

- FastMCP on PyPI (version 3.4.7, released 2026-08-10): https://pypi.org/project/fastmcp/
- FastMCP changelog — tool-transformation fixes in v3.2.4 (2026-04-14) and v3.3.0 (2026-05-15): https://github.com/jlowin/fastmcp/blob/main/docs/changelog.mdx
- The 2026-07-28 MCP specification (targeted by the FastMCP 4 beta): https://blog.modelcontextprotocol.io/posts/2026-07-28/
- FastMCP tool transformation documentation: https://gofastmcp.com/patterns/tool-transformation
- Direct inspection of the installed `fastmcp` 3.4.7 package (`ArgTransform` and `forward` docstrings) and the executed code above, run 2026-08-16.
