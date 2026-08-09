# I Gave My Tool a Default Value. The OpenAI Agents SDK Told the Model It Was Required Anyway.

Here is a tool with two required parameters and two optional ones:

```python
@function_tool
def search_flights(origin: str, destination: str,
                   max_price: float = 500.0, nonstop: bool = False) -> str:
    ...
```

`max_price` and `nonstop` have defaults. In plain Python, you can call this function with just an origin and a destination. So you would expect the schema the model sees to mark those two as optional. It does not. The [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) sends the model a schema where all four parameters are `required` — and it does that on purpose, by default, on every function tool you write.

I only went looking because the SDK has been moving fast. Version 0.19.4 [landed on PyPI on 2026-08-05](https://pypi.org/project/openai-agents/), the fifth release in about two weeks (0.19.0 through 0.19.4 all shipped between July 27 and August 5). When a dependency your agents call on every turn is releasing that often, it is worth knowing exactly what it hands the model. The tool schema turned out to be the surprising part.

## What `@function_tool` actually builds

When you decorate a function, the SDK does not just grab its name. Per the [tools documentation](https://openai.github.io/openai-agents-python/tools/), it uses "Python's `inspect` module to extract the function signature, along with [`griffe`](https://mkdocstrings.github.io/griffe/) to parse docstrings and `pydantic` for schema creation." Three libraries, one JSON Schema:

- `inspect` reads the parameter names, type hints, and defaults.
- `griffe` reads your docstring and pulls out the tool description and a description for each argument. It supports google, sphinx, and numpy styles, with automatic detection.
- `pydantic` builds a model from the signature and emits the JSON Schema.

That schema is what the model receives as the tool's `parameters`. The argument descriptions come straight from your docstring, which is why writing a real `Args:` block matters — it is not documentation for humans, it is prompt text for the model.

So far, so reasonable. The surprise is in the last step: pydantic emits the schema in **strict mode** by default.

## The rule that forces every parameter to be required

Strict mode is not an Agents SDK invention. It comes from OpenAI's [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) feature, which guarantees the model's tool-call arguments match your schema exactly. That guarantee comes with constraints. Two of them are:

1. Every `object` must set `additionalProperties: false`.
2. Every property listed under `properties` must appear in `required`. There is no such thing as an optional field in a strict schema.

The [OpenAI developer community](https://community.openai.com/t/schema-additionalproperties-must-be-false-when-strict-is-true/929996) has a long-running thread of people hitting the first rule the hard way. The second rule is the one that reshapes your tool signature: because a strict schema cannot express "optional," the SDK resolves the conflict by listing all your parameters as required — including the ones with Python defaults.

The `default` value does not disappear. It stays in the property definition. But `required` wins: the model is told it must produce a value for `max_price` on every call, default or not.

## Try it yourself

No API key, no network call. Building a `FunctionTool` and reading its `.params_json_schema` is a pure, local operation, so you can inspect exactly what the model would receive.

```bash
python -m venv venv && source venv/bin/activate
pip install "openai-agents==0.19.4"
python tool_schema.py
```

The script defines the flight-search tool three ways and prints the `required` list, the `additionalProperties` flag, and one representative property for each:

```python
from typing import Optional
from agents import function_tool

@function_tool
def search_flights(origin: str, destination: str,
                   max_price: float = 500.0, nonstop: bool = False) -> str:
    """Search for flights between two cities.

    Args:
        origin: IATA code of the departure airport.
        destination: IATA code of the arrival airport.
        max_price: Maximum ticket price in USD to consider.
        nonstop: If True, only return nonstop flights.
    """
    return "ok"

print(search_flights.params_json_schema["required"])
```

Here is the real, unedited output of the full script:

```
[1] strict schema (the default), strict_json_schema = True
  required: ['origin', 'destination', 'max_price', 'nonstop']
  additionalProperties: False
  max_price: {"default": 500.0, "description": "Maximum ticket price in USD to consider.", "title": "Max Price", "type": "number"}

[2] strict_mode=False, strict_json_schema = False
  required: ['origin', 'destination']
  additionalProperties: None
  max_price: {"default": 500.0, "description": "Maximum ticket price in USD to consider.", "title": "Max Price", "type": "number"}

[3] Optional[str] = None under strict mode
  required: ['city', 'when']
  additionalProperties: False
  when: {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Optional ISO timestamp; omit to search now.", "title": "When"}
```

Read the three blocks in order.

**Block [1] — the default.** All four parameters are `required`. `max_price` still carries its `default: 500.0`, but it is in the required list all the same. `additionalProperties` is `False`. This is the schema the model gets unless you say otherwise. The model has no signal that `max_price` and `nonstop` are skippable; from its point of view, a call without them is malformed.

**Block [2] — `strict_mode=False`.** Now `required` is just `['origin', 'destination']`, the two parameters without defaults, exactly as ordinary pydantic behaves. `additionalProperties` is gone (`None`). This is the schema most people picture when they write the function. You get it only by opting out of strict mode.

**Block [3] — the right way to be optional.** `when: Optional[str] = None` is *still* in `required`. Strict mode will not let it out. But look at its type: `{"anyOf": [{"type": "string"}, {"type": "null"}]}`. Because the type is nullable, the model can satisfy "required" by explicitly sending `null`. That is how you express "this argument can be omitted" to a strict schema — not with a default, but with a type that admits `null`.

## So how do you actually make a parameter optional?

The takeaway from block [3] is the practical fix. Under strict mode, a Python default does not make a parameter optional to the model — a nullable type does. If you want the model to be able to skip an argument, annotate it as `Optional[...]` (or `X | None`). The parameter stays in `required`, but the model can pass `null`, and your function's default still applies on the Python side when the SDK deserializes the call.

If you instead rely on a bare default like `max_price: float = 500.0` with no nullable type, you are telling the model two contradictory things: "you must send this" (via `required`) and "here is a default" (via `default`). The model resolves that by usually sending a value — often just echoing your default, sometimes inventing one. Either way you have lost the behavior you wanted, which was for the model to leave it alone.

## When flipping strict off is the right call

`strict_mode=False` is a legitimate escape hatch, and the SDK exposes it precisely because strict schemas cannot represent everything. Strict Structured Outputs disallow a range of JSON Schema features — open-ended objects, certain composite constraints — so a tool with a genuinely dynamic argument shape may need it off. The cost is real, though: you give up the guarantee that arguments validate against your schema, which means you inherit the old failure mode of the model sending arguments that do not fit, and you handle that yourself. For most tools, keeping strict on and making optional arguments nullable is the cleaner path.

The broader point is that the schema is a contract you are writing on the model's behalf, and the SDK's defaults edit that contract in ways your Python signature does not show. A default value reads as "optional" to you and as "required" to the model. Four days into the latest release, that gap is worth ten lines of code to see for yourself before you ship the tool.

## Key Takeaways

- The OpenAI Agents SDK builds tool schemas with `inspect` + `griffe` + `pydantic`, and emits them in **strict mode by default** (`strict_json_schema=True`).
- Strict [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) require every property to be `required` and every object to set `additionalProperties: false`. The SDK therefore marks **parameters with Python defaults as required**.
- A Python default does **not** make an argument optional to the model. A **nullable type** (`Optional[str]`) does — the argument stays required but can be satisfied with `null`.
- `@function_tool(strict_mode=False)` restores ordinary pydantic behavior (defaults become non-required, `additionalProperties` is dropped) at the cost of the strict-validation guarantee.
- Your docstring's `Args:` block is prompt text: griffe copies each argument description into the schema the model reads.

*Every schema shown above was captured directly from `openai-agents==0.19.4` on Python 3.11; nothing was hand-edited.*

Sources: [OpenAI Agents SDK — Tools](https://openai.github.io/openai-agents-python/tools/) · [openai-agents on PyPI (0.19.4, 2026-08-05)](https://pypi.org/project/openai-agents/) · [OpenAI Structured Outputs guide](https://platform.openai.com/docs/guides/structured-outputs) · [OpenAI community: additionalProperties must be false when strict is true](https://community.openai.com/t/schema-additionalproperties-must-be-false-when-strict-is-true/929996) · [griffe](https://mkdocstrings.github.io/griffe/)
