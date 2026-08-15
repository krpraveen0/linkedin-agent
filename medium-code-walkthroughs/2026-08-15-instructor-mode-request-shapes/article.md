# I Gave Instructor One Pydantic Model. Its Mode Setting Sent My LLM Three Different Requests.

You write a Pydantic model, hand it to [Instructor](https://python.useinstructor.com/), and get typed data back from an LLM. It feels like one operation: model in, object out. It isn't. Between your model and the network call, Instructor decides *how* to ask — and depending on that decision, the same `User` model goes out as a function-calling tool, a `response_format` flag, or a wall of instructions stapled onto your prompt. There are 38 of those decisions available, and you usually don't make it yourself.

I installed Instructor 1.15.4 and stopped the code one step before the HTTP call to see exactly what each choice puts on the wire. Here is what came out.

## The one line that hides a decision

The modern Instructor entry point is `instructor.from_provider("openai/gpt-4o")`, a single call that wraps a client and, per the [PyPI listing](https://pypi.org/project/instructor/) for the June 28, 2026 release, works across OpenAI, Anthropic, Google, Ollama, Groq and others through one interface. You never say *how* you want structured output. Instructor's [patching docs](https://github.com/567-labs/instructor/blob/main/docs/concepts/patching.md) put it plainly: "Instructor automatically selects the best mode for each provider." For OpenAI that default is `Mode.TOOLS` — the provider's function/tool-calling API.

That "mode" is the whole game. It is also why this is worth looking at *now*: as of the 1.15.x line, Instructor's internals were rebuilt into a provider-owned, registry-based architecture. The package ships a `v2/` core whose own README states that the public modules under `instructor/core`, `instructor/processing`, and friends "are compatibility facades over v2-owned implementations." In plain terms, the map from *mode* to *actual request* is now owned per provider, dispatched through a registry. The public API you call is stable; the thing underneath that turns your model into bytes is the part that got rewritten.

So let's look at the bytes.

## Watching the request get built

Instructor's request-building function is `handle_response_model`. It takes your model and a mode and returns the keyword arguments it would pass to the provider's chat call. Calling it directly needs no API key and makes no network request — it is the real code path a patched client uses, stopped one step early.

```python
import json
from pydantic import BaseModel, Field
from instructor import Mode
from instructor.processing.response import handle_response_model

class User(BaseModel):
    name: str = Field(description="The person's full name")
    age: int

def build(mode: Mode) -> dict:
    _, kwargs = handle_response_model(
        User, mode=mode,
        messages=[{"role": "user", "content": "Extract: Jane Doe is 30"}],
    )
    return kwargs

print("Instructor exposes", len([m for m in Mode]), "modes.\n")
for mode in (Mode.TOOLS, Mode.JSON, Mode.MD_JSON):
    kw = build(mode)
    print("=" * 64)
    print("Mode:", mode.value)
    print("  tools sent?          ", "tools" in kw)
    print("  tool_choice forced?  ", kw.get("tool_choice", "no"))
    print("  response_format:     ", kw.get("response_format", "none"))
    print("  # messages:          ", len(kw["messages"]), "(started with 1)")
```

Real output:

```
Instructor exposes 38 modes.

================================================================
Mode: tool_call
  tools sent?           True
  tool_choice forced?   {'type': 'function', 'function': {'name': 'User'}}
  response_format:      none
  # messages:           1 (started with 1)
================================================================
Mode: json_mode
  tools sent?           False
  tool_choice forced?   no
  response_format:      {'type': 'json_object'}
  # messages:           2 (started with 1)
================================================================
Mode: markdown_json_mode
  tools sent?           False
  tool_choice forced?   no
  response_format:      none
  # messages:           2 (started with 1)
```

Three modes, three structurally different requests from one model:

- **`TOOLS`** attaches a `tools` array and a *forced* `tool_choice` pinning the model to a function named `User`. The message list is untouched — the schema travels as an API parameter, not as text.
- **`JSON`** sends no tools. It sets `response_format` to `{"type": "json_object"}` and grows the message list from one to two.
- **`MD_JSON`** sets no `response_format` at all, yet the message list also grew to two. The schema went *somewhere* — just not into an API field.

The count itself is worth pausing on: 38 modes, most of them provider-specific (`ANTHROPIC_TOOLS`, `GEMINI_JSON`, `MISTRAL_STRUCTURED_OUTPUTS`, and so on). The `from_provider` string you pass is what quietly narrows those 38 down to one.

## Where did my schema go? Into the prompt.

For the two JSON modes, the "extra message" is the schema. Print the messages and the mechanism is obvious.

```python
from pydantic import BaseModel, Field
from instructor import Mode
from instructor.processing.response import handle_response_model

class User(BaseModel):
    name: str = Field(description="The person's full name")
    age: int

_, kw = handle_response_model(
    User, mode=Mode.MD_JSON,
    messages=[{"role": "user", "content": "Extract: Jane Doe is 30"}],
)
for m in kw["messages"]:
    print(f"[{m['role']}]"); print(m["content"].strip(), "\n")

_, kwt = handle_response_model(User, mode=Mode.TOOLS,
                              messages=[{"role": "user", "content": "x"}])
fn = kwt["tools"][0]["function"]
print("tool name:       ", fn["name"])
print("tool description:", repr(fn["description"]))
```

Real output (the schema block is shown trimmed for space; in reality it is the full JSON Schema of `User`. The outer fence here is four backticks so the model-facing triple-backtick instruction renders literally):

````text
[system]
As a genius expert, your task is to understand the content and provide
            the parsed objects in json that match the following json_schema:
            { ...full JSON Schema of User... }
            Make sure to return an instance of the JSON, not the schema itself

[user]
Extract: Jane Doe is 30

Return the correct JSON response within a ```json codeblock. not the JSON_SCHEMA

tool name:        User
tool description: 'Correctly extracted `User` with all the required parameters with correct types'
````

Two things stand out. First, `MD_JSON` doesn't just prepend a system message — it **edits your user message**, appending a line (shown in the output above) that tells the model to return its answer inside a fenced json code block, not the schema. The prompt you thought you controlled has an extra sentence in it that you didn't write. Second, in `TOOLS` mode the tool is named after your class, and because `User` has no docstring, Instructor generates the description itself: *"Correctly extracted `User` with all the required parameters with correct types."* That canned sentence is what the model reads as the tool's purpose. If you care what the model thinks the tool is for, write a docstring.

## The mode you ask for isn't always the mode you get

Instructor also exposes `Mode.TOOLS_STRICT`, meant to lean on OpenAI's strict structured-outputs schema. I expected it to differ from `TOOLS`. At the request-building layer, it doesn't.

```python
import json
from pydantic import BaseModel
from instructor import Mode
from instructor.processing.response import handle_response_model

class User(BaseModel):
    name: str
    age: int

def req(mode):
    _, kw = handle_response_model(User, mode=mode,
                                 messages=[{"role": "user", "content": "x"}])
    return json.dumps(kw, sort_keys=True, default=str)

print("TOOLS request == TOOLS_STRICT request?", req(Mode.TOOLS) == req(Mode.TOOLS_STRICT))
print("'strict' anywhere in the request?     ", "strict" in req(Mode.TOOLS_STRICT))
```

Real output:

```
TOOLS request == TOOLS_STRICT request? True
'strict' anywhere in the request?      False
```

Byte for byte identical, with no `strict` flag in sight. That isn't a bug — it is the provider-owned design showing through. Strict-schema handling lives in the provider handler (`instructor/v2/providers/openai/handlers.py` builds the `additionalProperties: False` / `strict: True` payload), and Instructor's per-provider capability tables remap requested modes to what a provider actually supports — the OpenAI-compatible spec literally aliases `TOOLS_STRICT` back to `TOOLS`. The mode you name is a *request*, resolved against a provider's real capabilities. On a provider or code path that doesn't wire strictness in, asking for `TOOLS_STRICT` gets you plain tool calling and no error telling you so.

## Why any of this matters

The abstraction is genuinely useful — one `from_provider` line, and portable structured output across a dozen backends. But the abstraction has a cost you pay at debugging time. When a local model returns malformed JSON, or an Ollama model ignores your schema, the fix is often not a better prompt — it's a different mode. `TOOLS` needs a model trained for function calling; a smaller local model may do far better in `JSON` or `MD_JSON`, where the schema is spelled out in the prompt instead of assumed in a tool interface. Knowing that `MD_JSON` rewrites your user turn, or that `JSON` injects a "genius expert" system message, tells you what your real prompt is when you go to tune it. And knowing that a mode can silently degrade to a weaker one keeps you from trusting a guarantee you never actually got.

None of this requires an API key to inspect. `handle_response_model` will show you your real request any time you want to know what your framework is saying on your behalf.

## Try It Yourself

```bash
python -m venv venv && source venv/bin/activate
pip install "instructor==1.15.4"   # pulls pydantic 2.13, openai 2.54
python instructor_modes.py
```

`instructor_modes.py` is the first code block above. It prints the mode count and the three request shapes with no network call and no key. Swap `Mode.TOOLS/JSON/MD_JSON` for any of the 38 members of `instructor.Mode` to see what your provider's default actually sends. The exact injected strings and the mode count are tied to version 1.15.4 — pin the version if you want the output to match byte for byte.

## Key Takeaways

- Instructor turns one Pydantic model into structurally different requests depending on its **mode**: `TOOLS` sends a forced tool call, `JSON` sends a `response_format` flag plus an injected schema message, `MD_JSON` sends neither and instead **rewrites your prompt**.
- You rarely choose the mode. `from_provider` picks a provider-appropriate default (`TOOLS` for OpenAI), because as of the 1.15.x rewrite the mode-to-request mapping is owned per provider through a registry.
- In `TOOLS` mode the tool is named after your class and gets an auto-generated description unless you write a docstring.
- A requested mode is resolved against provider capabilities: `TOOLS_STRICT` produced a byte-identical request to `TOOLS` in the request builder, with no `strict` flag — verify, don't assume.
- `handle_response_model(YourModel, mode=...)` lets you inspect the exact request offline, which is the fastest way to debug structured-output failures.

*Sources:* [Instructor on PyPI (1.15.4, June 28 2026)](https://pypi.org/project/instructor/) · [Instructor patching / modes docs](https://github.com/567-labs/instructor/blob/main/docs/concepts/patching.md) · [Instructor GitHub repository](https://github.com/567-labs/instructor) · behavior verified directly against the installed `instructor==1.15.4`, `pydantic==2.13.4`, `openai==2.54.0` on Python 3.11.
