# Parallel tool-call failure semantics across three agent frameworks

Runnable code for the deep-dive article in `article.md`.

The question: when a model emits several tool calls in one turn and **one of them
fails**, what happens to the others, and is the resulting conversation history
still something a provider will accept?

Each script uses a scripted fake model. **No API key, no network, no GPU.**

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install \
  "langgraph==1.2.10" \
  "langchain-core==1.5.3" \
  "pydantic-ai-slim==2.27.0" \
  "openai-agents==0.19.4"
```

Python 3.11 was used. Exact versions that produced the output below:

```
langchain-core==1.5.3
langgraph==1.2.10
langgraph-prebuilt==1.1.0
openai==2.53.0
openai-agents==0.19.4
pydantic-ai-slim==2.27.0
```

## Run

```bash
./venv/bin/python 01_langgraph_toolnode.py
./venv/bin/python 02_openai_agents_isolation.py
./venv/bin/python 03_pydantic_ai_repair.py
./venv/bin/python 04_reconcile.py
```

## The scenario

Every script runs the same batch:

| tool | behavior | call id |
| --- | --- | --- |
| `lookup_user` | sleeps 50ms, succeeds | `call_a` |
| `charge_card` | raises `ValueError("gateway timeout")` immediately | `call_b` |

Each script reports three things: what the framework returned or raised, what
landed in the persisted history, and whether the sibling's tool body actually ran
to completion (tagged with *which phase of the program was active when it
finished*, which is how the leak in script 01 becomes visible).

## Captured output

All output below was produced by running the scripts as written.

### 01_langgraph_toolnode.py

```
langgraph==1.2.10 langgraph-prebuilt==1.1.0 langchain-core==1.5.3

--- default handle_tool_errors ---
  graph RAISED ValueError: gateway timeout
  at the moment the graph returned, completed tool bodies: none
  persisted messages: 1
    AIMessage tool_calls=['call_a', 'call_b']
  orphaned tool_call_ids: ['call_a', 'call_b']  -> provider would have REJECTED
  after draining the event loop:  ['lookup_user(u_1) finished during run="after \'default handle_tool_errors\' returned"']

--- handle_tool_errors=True ---
  graph completed
  at the moment the graph returned, completed tool bodies: ["lookup_user(u_1) finished during run='handle_tool_errors=True'"]
  persisted messages: 3
    AIMessage tool_calls=['call_a', 'call_b']
    ToolMessage id='call_a' status='success' 'user u_1: ok'
    ToolMessage id='call_b' status='error' "Error: ValueError('gateway timeout')\n Please fix yo..."
  orphaned tool_call_ids: none  -> provider would have accepted
  after draining the event loop:  ["lookup_user(u_1) finished during run='handle_tool_errors=True'"]
```

Under the default, the checkpoint holds only the assistant turn: both call ids are
orphaned, and `call_a`'s successful result is gone. The last line shows the
abandoned sibling finishing **after** its own graph invocation had already raised
and returned. It was never cancelled.

### 02_openai_agents_isolation.py

```
openai-agents==0.19.4 openai==2.53.0

--- default failure_error_function ---
  run completed: final_output='done'
  items in history: 6
    function_call        call_id='call_a' name='lookup_user'
    function_call        call_id='call_b' name='charge_card'
    function_call_output call_id='call_a' output='user u_1: ok'
    function_call_output call_id='call_b' output='An error occurred while running the tool. Please tr...'
  orphaned call_ids: none  -> provider would have accepted
  at the moment the run returned, completed tool bodies: ["lookup_user(u_1) finished during run='default failure_error_function'"]
  after draining the event loop:  ["lookup_user(u_1) finished during run='default failure_error_function'"]

--- failure_error_function=None ---
  run RAISED UserError: Error running tool charge_card: gateway timeout
  no RunResult was produced, so the caller has no history object to persist
  at the moment the run returned, completed tool bodies: ["lookup_user(u_1) CANCELLED during run='failure_error_function=None'"]
  after draining the event loop:  ["lookup_user(u_1) CANCELLED during run='failure_error_function=None'"]
```

By default the exception becomes a tool output, so the batch stays paired. With
that disabled, the sibling receives `asyncio.CancelledError` rather than running
on. Contrast with script 01.

### 03_pydantic_ai_repair.py

```
pydantic-ai-slim==2.27.0

--- run 1: cancelled while charge_card is still running ---
  run cancelled
    ToolCallPart   id='call_a' name='lookup_user'
    ToolCallPart   id='call_b' name='charge_card'
    ToolReturnPart id='call_a' outcome='success' 'user u_1: ok'
  dangling tool calls in the captured history: ['call_b']
  -> provider would have REJECTED this history

--- run 2: same history handed back to the agent ---
  run completed: 'done'
  what the model actually received on its first call of run 2:
      ToolCallPart   id='call_a' name='lookup_user'
      ToolCallPart   id='call_b' name='charge_card'
      ToolReturnPart id='call_a' outcome='success' 'user u_1: ok'
      ToolReturnPart id='call_b' outcome='interrupted' SYNTHESIZED 'The tool call was interrupted before a result was...'
  dangling tool calls in what was sent: none
  -> provider would have accepted this history
```

The completed sibling's result survives the cancellation, and the genuinely
dangling call is closed out with a synthesized `outcome='interrupted'` return on
the way to the model.

### 04_reconcile.py

```
--- crashed before any result was recorded ---
  2 messages, orphans: ['call_a', 'call_b']
  a provider would reject this with, in OpenAI's wording:
    An assistant message with 'tool_calls' must be followed by tool
    messages responding to each 'tool_call_id'. The following
    tool_call_ids did not have response messages: call_a, call_b
  after repair: 4 messages, orphans: none
  repair is idempotent: True

--- one sibling landed, one did not ---
  3 messages, orphans: ['call_b']
  a provider would reject this with, in OpenAI's wording:
    An assistant message with 'tool_calls' must be followed by tool
    messages responding to each 'tool_call_id'. The following
    tool_call_ids did not have response messages: call_b
  after repair: 4 messages, orphans: none
  repair is idempotent: True
```

A framework-agnostic pairing check and repair over plain OpenAI-shaped message
dicts, for stacks that do not do this for you. Idempotence matters: this pass
runs before every request, and a repair producing different bytes each time would
invalidate the provider's prompt-cache prefix on every turn.

## Notes

- Scripts 01 and 02 deliberately let an abandoned task outlive the call that
  started it, then drain the event loop and re-check. That is the mechanism that
  distinguishes "cancelled" from "still running with nowhere to put the result".
- `charge_card` in script 03 sleeps 5s so the run can be cancelled mid-flight;
  the script cancels after 0.3s.
- Timings are the only source of variability. The sleeps are chosen with wide
  margins, but on a heavily loaded machine the exact interleaving in script 01's
  "at the moment the graph returned" line could differ.

## Diagrams

- `fig1-pairing-contract.svg` — paired vs orphaned history, and why an orphan is permanent
- `fig2-three-mechanisms.svg` — the three internal paths side by side
- `fig3-repair-pass.svg` — where Pydantic AI's repair pass sits in the request path
