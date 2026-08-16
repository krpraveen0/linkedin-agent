# FastMCP tool transformation: hide and inject tool arguments

Companion code for the Medium article *"I Handed My Agent a Tool With an API-Key Argument. FastMCP Hid It From the Model Before It Could Ask."* (2026-08-16).

These scripts run a real in-memory FastMCP client<->server round-trip to show how `Tool.from_tool()` + `ArgTransform` change the schema a connected client (the model) sees: renaming arguments, hiding a secret and injecting it server-side, and wrapping a tool in your own validation logic. **No API key and no network** — FastMCP's in-memory `Client` talks directly to the server object.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install "fastmcp==3.4.7"    # pulls mcp 1.29.0, pydantic 2.13.4
```

Verified environment: Python 3.11.15, `fastmcp==3.4.7`, `mcp==1.29.0`, `pydantic==2.13.4`.

## Run

```bash
python transform_schema.py   # the schema the model sees, before vs after
python transform_call.py     # hidden args injected server-side; caller can't set them
python transform_fn.py       # transform_fn + forward() adds validation logic
```

Each script prints to stdout. FastMCP logs a rich traceback to **stderr** for the one intentionally-rejected call in `transform_call.py`; append `2>/dev/null` to see stdout alone.

## Real captured output

### `transform_schema.py`

```
 get_forecast | model sees params: ['lat', 'lon', 'appid', 'units']  required: ['lat', 'lon', 'appid']
     forecast | model sees params: ['latitude', 'longitude']  required: ['latitude', 'longitude']
```

The raw tool exposes four parameters and lists the secret `appid` as required. The transformed tool exposes two clearly named parameters; the secret and the units flag are gone from the model's view.

### `transform_call.py` (stdout)

```
model passed:  {latitude: 48.85, longitude: 2.35}
function saw:  {"lat": 48.85, "lon": 2.35, "units": "metric", "used_key": "sk-d..."}
inject attempt: ToolError - Error calling tool 'forecast': Got unexpected keyword argument(s): appid
```

The underlying function received the hidden `units="metric"` and the injected key (`used_key` shows `sk-d...`), even though the caller sent only latitude/longitude. Passing `appid` explicitly is rejected, because a hidden argument is not part of the transformed tool's schema.

### `transform_fn.py`

```
valid   -> {"lat": 48.85, "lon": 2.35, "units": "metric", "used_key": "sk-d..."}
bad lat -> ToolError - Error calling tool 'forecast': latitude 999 out of range
```

A `transform_fn` runs before the upstream call and forwards through `forward()`, so an out-of-range latitude is rejected while a valid call still forwards with the hidden units and key injected.

## Notes

- Behavior verified by direct inspection of the installed `fastmcp` 3.4.7 package (the `ArgTransform` docstring states `hide=True` will "hide this argument from clients but pass a constant value to parent") and by the executed round-trips above, on 2026-08-16.
- This code and its output were generated and independently re-executed by an automated daily pipeline. The process validates traceability, freshness, and code execution — not deep domain correctness. A human accuracy pass is recommended before treating this as authoritative.
