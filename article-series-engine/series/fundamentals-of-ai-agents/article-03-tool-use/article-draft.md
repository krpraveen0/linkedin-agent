# Tool use, for real: the mechanism behind "agents can take actions"

*Every guide to AI agents says some version of "agents can call APIs, search the web, run code." Almost none of them show you the actual mechanism - the shape of the request, how execution really works, or what happens when the model asks for a tool that doesn't exist. This one does, and you still don't need an API key.*

## Step 0: What you'll need

Python 3.9+. Same as the last two articles - no API key required for the core lesson.

## Step 1: The real shape, from Anthropic's own documentation

Here's the actual mechanism, not the marketing summary. You define a tool with a name, a description, and an `input_schema` - a JSON Schema describing what arguments it takes. When the model decides to use it, the API response contains a `tool_use` block: the tool's name, plus a JSON object of arguments. Your application - not the model - executes the operation and sends the output back in a `tool_result` block on the next request. The model never sees your implementation. It only ever sees the schema you gave it and the result you send back.

That's the whole mechanism. Three pieces: a schema, an execution step your code owns, and a result that flows back in a specific shape. Everything in this article builds and runs that exact round trip.

Worth sitting with one detail in that description: the model never executes anything on its own. It emits a structured request; your code decides whether and how to actually run it. That's not an incidental implementation detail - it's the entire reason tool use can be made safe at all. If the model directly ran arbitrary code or API calls, there would be no place to check whether a request was reasonable before it happened. Because execution is always your code's job, every tool call is a checkpoint, whether or not you're using it as one yet. This series' companion series, Design Multi-Agent Systems, spends a full article on exactly what happens when that checkpoint gets skipped - but the checkpoint exists here, at the single-agent level, before any of that complexity is even in the picture.

## Step 2: Define a tool, and the real function behind it

Save this as `tool_use.py`:

```python
TOOL_SCHEMA = {
    "name": "check_ticket_status",
    "description": "Look up the current status of a support ticket by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "e.g. 'TICKET-123'"},
        },
        "required": ["ticket_id"],
    },
}

TICKET_DATABASE = {"TICKET-123": "open", "TICKET-456": "resolved"}

def check_ticket_status(ticket_id: str) -> str:
    if ticket_id not in TICKET_DATABASE:
        raise KeyError(f"no such ticket: {ticket_id}")
    return TICKET_DATABASE[ticket_id]
```

Notice `check_ticket_status` is a completely ordinary Python function. Nothing about it is "agentic." That's the point - the intelligence is entirely in *deciding when to call it*, not in the function itself.

Worth noting why the schema is worded the way it is, since this matters more than it looks like it should. The tool name is `check_ticket_status` - a specific verb and a specific noun, not something generic like `handle_ticket` or `process`. Production guidance on this is consistent: wrong-tool selection traces back to ambiguous schemas almost every time, and the fix is making names specific enough that two different tools couldn't plausibly both seem right for the same request. If this system ever grew a second tool - say, `close_ticket` - a vague name like `ticket_action` for either one would make it genuinely harder for a model to pick correctly, not just harder for a human reading the code.

## Step 3: Model the tool_use and tool_result blocks

Still in `tool_use.py`:

```python
@dataclass(frozen=True)
class ToolUseBlock:
    name: str
    input: dict

def decide_tool_call(user_message: str) -> ToolUseBlock:
    if "TICKET-" in user_message:
        raw = user_message.split("TICKET-")[1].split()[0]
        ticket_id = "TICKET-" + "".join(ch for ch in raw if ch.isalnum())
        return ToolUseBlock(name="check_ticket_status", input={"ticket_id": ticket_id})
    raise ValueError("no ticket ID found in message")

@dataclass(frozen=True)
class ToolResultBlock:
    content: str
    is_error: bool = False

def execute_tool_call(block: ToolUseBlock) -> ToolResultBlock:
    if block.name != TOOL_SCHEMA["name"]:
        return ToolResultBlock(content=f"Error: unknown tool '{block.name}'", is_error=True)
    try:
        status = check_ticket_status(**block.input)
        return ToolResultBlock(content=f"Ticket status: {status}")
    except KeyError as e:
        return ToolResultBlock(content=f"Error: {e}", is_error=True)
    except TypeError as e:
        return ToolResultBlock(content=f"Error: malformed arguments - {e}", is_error=True)
```

`decide_tool_call` is the deterministic stand-in for the model - same role as `decide_next_action` in Articles 01 and 02, just now returning a tool name and arguments instead of a bare action string. Run the whole round trip:

```
A real, working round trip:
  model requested: ToolUseBlock(name='check_ticket_status', input={'ticket_id': 'TICKET-123'})
  tool_result: ToolResultBlock(content='Ticket status: open', is_error=False)
```

That's a complete, real tool-use cycle. The "model" decided which tool and what arguments. Your code ran the actual function. The result came back in a structured block, ready to hand back to the model in a real system.

## Step 4: What happens when the model asks for a tool that doesn't exist

This is the part almost nothing covers with actual code. Anthropic's own production guidance names this directly: the model can hallucinate a tool call, rare but real, especially when tool schemas overlap or a request is ambiguous. Here's what that looks like and what it takes to handle it.

Save this as `broken_tool_calls.py`:

```python
def naive_execute_tool_call(block):
    if block.name == "check_ticket_status":
        return check_ticket_status(**block.input)
    # no else branch at all
```

Now call it with a tool name that has a realistic typo - `check_ticket_stauts` instead of `check_ticket_status`, exactly the shape a hallucinated call actually takes:

```
Without validation (naive_execute_tool_call):
  returned: None
  -> no exception, no error, nothing. It silently returns None,
     as if the call simply succeeded with no result.
```

No crash. No error. It just quietly returns nothing, and whatever code called it has no way to tell "the tool succeeded with no output" apart from "the tool name was wrong and nothing happened." That's arguably worse than a crash - a crash at least tells someone something went wrong.

Compare that to the version from Step 3, with an actual check against the real tool list:

```
With validation (execute_tool_call from tool_use.py):
  ToolResultBlock(content="Error: unknown tool 'check_ticket_stauts' - not in the available tool list", is_error=True)
  -> the model gets an informative error back and can retry
```

`is_error=True` isn't decorative - it's the exact field the real API uses to tell the model "this didn't work, here's why," so it can try again with a corrected tool name instead of confidently reporting a result that never actually happened.

<image src="file-upload://3a6c633a-e23a-8107-93f4-00b2de223b44"></image>

## Step 5: The other way tool calls break - malformed arguments

One more realistic failure: the model asks for the right tool, but leaves out a required argument.

```
Case 2: malformed arguments (missing the required field)
  With validation:
    ToolResultBlock(content="Error: malformed arguments - check_ticket_status() missing 1 required positional argument: 'ticket_id'", is_error=True)
```

The fix is the same shape as Step 4's fix: let Python's own `TypeError` - which fires automatically when a required argument is missing - become an informative `tool_result` instead of an unhandled crash. You don't need to hand-write validation for every possible missing field. The function signature and a `try/except` around the call already know.

## Step 6: The two rules this article actually teaches

1. **Validate the tool name against your real list before executing anything.** A model asking for a tool that doesn't exist should get a clear error back, not a silent `None` and not an unhandled crash.
2. **Let real exceptions become informative tool_results, not unhandled crashes.** A missing argument, a bad type, a lookup failure - Python already tells you about all of these. The only work is catching them and packaging the message the way Step 3 does, with `is_error=True` so whatever's on the other end of this round trip knows to treat it as a failure, not a result.

One thing worth knowing exists, even though it's out of scope for a single tool call: as the number of tools an agent has access to grows, and as tasks need several tool calls chained together, the round trip in this article - one tool_use, one tool_result, repeat - starts costing a full model inference pass for every single call, with intermediate results piling up in context whether they end up mattering or not. Anthropic's own more advanced tooling addresses this by having the model write code that orchestrates several tool calls at once, processing results before anything returns to the model's context at all. That's a genuinely different problem from the one this article solves, and it's only worth reaching for once the basic round trip here is solid - which is exactly why it's a "worth knowing exists" footnote here, not a Step 7.

## What this looks like today

Look at any tool-calling code you've written or are about to write, and check specifically: what happens right now if the tool name doesn't match anything real? If the honest answer involves an unhandled exception, or worse, a quiet `None` that looks like success, you've got exactly the gap Step 4 walked through - and the fix is the same few lines either way.

Do the same check for arguments, not just names. Call your own tool-execution code with an empty or partial input dict, the way Step 5 did here, and see what actually happens. If Python's own `TypeError` isn't caught somewhere and turned into a message you'd be comfortable sending back, that's the second gap this article closes, sitting in your code right now.

The next article in this series is where the toy in-memory dictionaries from this one stop being enough: two genuinely different problems both get called "memory," and conflating them is where a lot of real agents actually break.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Fundamentals of AI Agents

1. What actually makes something an agent? A testable definition, not an analogy — not yet published
2. The agent loop, built from scratch: observe, decide, act, and actually stop — not yet published
3. **Tool use, for real: the mechanism behind "agents can take actions"** *(this article)*
4. Two things people call "memory," and why conflating them breaks agents — not yet published
5. Reactive vs. planning agents, and how to actually choose — not yet published
6. Stopping conditions: why "cap max_steps" is the least of it — not yet published
7. Evaluating a single agent: what to actually measure before you add a second one — not yet published
8. Building one real agent end to end, and what comes after it: multi-agent systems — not yet published

## References

1. Tool use with Claude, Claude Platform Docs
   https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
2. How tool use works, Claude Platform Docs
   https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works
