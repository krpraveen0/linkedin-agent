# I Handed One Support Conversation to a Second Agent in Three Frameworks. It Received 574, 122, and 233 Tokens.

The setup is the most ordinary thing in multi-agent engineering. A triage agent takes a customer message, calls one tool to look up the order, decides this is a refund case, and transfers to a refund specialist. Two agents, one tool call, one handoff.

I built that exact flow three times — once with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python), once with [Microsoft's Agent Framework](https://github.com/microsoft/agent-framework), once with [LangGraph](https://github.com/langchain-ai/langgraph) — with scripted models so every run is byte-for-byte reproducible, and I recorded the exact request each framework built for the *second* agent.

The refund agent received 574 tokens in one framework, 122 in another, and 233 in the third. In two of the three, the order record the triage agent had just fetched was not reachable at all. In one configuration of one framework, the transcript that reached the parent graph contained a tool result with no tool call requesting it — the kind of message list a provider rejects.

Those three numbers are not perfectly commensurable, for reasons I spell out in the methodology below. What is not in doubt is the part that costs money and correctness: one framework forwarded the order record and two dropped it.

None of this is a bug. These are three defensible answers to a question with no obvious right one, and the frameworks have quietly picked opposite defaults. If you have shipped a multi-agent system on any of them, you inherited one of these answers without being asked.

Everything below runs on CPU with no API keys. The versions are the ones current on the day I ran it: `openai-agents==0.22.0` ([released 2026-08-19](https://pypi.org/project/openai-agents/0.22.0/)), `agent-framework-core==1.15.0` with `agent-framework-orchestrations==1.1.1` ([both 2026-08-21](https://pypi.org/project/agent-framework-orchestrations/1.1.1/)), and `langgraph==1.2.11` ([2026-08-11](https://pypi.org/project/langgraph/1.2.11/)) with `langchain-core==1.6.0`.

## The scenario, held constant

One user message:

> Order A-1183 arrived damaged. I want a refund.

One tool, `lookup_order`, that returns a realistic order record — line items, shipping, payment, refund policy. Under GPT-2 BPE it measures **310 tokens**. That number matters, because the whole question is whether those 310 tokens survive the handoff.

The triage agent calls `lookup_order`, then transfers to the refund agent, which answers. Three model calls, always identical, because every model here is a scripted test double rather than a live LLM.

For the OpenAI Agents SDK I used [`agents.testing.ScriptedModel`](https://github.com/openai/openai-agents-python/blob/main/src/agents/testing/model.py), which ships in the SDK itself; its `.calls` property records each request at the provider-neutral `Model` boundary, including the exact `input` list. For the other two frameworks I wrote equivalent recording fakes. Nothing below is a reconstruction of what a framework "would" send; it is what the framework built, printed.

Token counts come from the GPT-2 BPE model that ships inside the `blingfire` wheel, applied to a canonical JSON dump of each request with per-run message UUIDs stripped. Three caveats bound what those numbers mean.

GPT-2 BPE is not any current production tokenizer, so the counts are a consistent yardstick, not a billing estimate.

Each framework serializes messages differently, and the difference is large. The *same* single user sentence costs **25 tokens as an Agents SDK input item, 46 as a LangGraph `HumanMessage.model_dump()`, and 59 as an Agent Framework `Message.to_dict()`** — a 2.4× spread before a word of content changes.

The frameworks also disagree on where the system prompt lives. The Agents SDK's `ModelCall` stores `system_instructions` separately from `input`, and the Agent Framework's counts exclude it too; LangGraph's include it, because the prompt arrives as a `SystemMessage` in the message list. In the LangGraph figures below, 37 tokens of every count are the string "You process refunds."

Cross-framework totals are therefore directional, and the within-framework comparisons are the rigorous ones. What survives all three caveats is the result that matters: only one of the three frameworks put the 310-token order record in front of the second agent.

## Three frameworks, three answers

### OpenAI Agents SDK: the receiving agent inherits everything

The SDK's [handoffs documentation](https://github.com/openai/openai-agents-python/blob/main/docs/handoffs.md) is explicit about the default: "When a handoff occurs, it's as though the new agent takes over the conversation, and gets to see the entire previous conversation history."

Running it confirms the doc, and shows what "entire" includes:

```
-- A. DEFAULT (no filter, nest_handoff_history=False) ---------------------
input items handed to Refund_agent: 5
  [0] message role=user      Order A-1183 arrived damaged. I want a refund.
  [1] function_call        name=lookup_order call_id=call_lookup_1
  [2] function_call_output call_id=call_lookup_1 output={ "order_id": "A-1183", "customer_id": …
  [3] function_call        name=transfer_to_refund_agent call_id=call_handoff_1
  [4] function_call_output call_id=call_handoff_1 output={"assistant": "Refund_agent"}
  order record reachable by Refund_agent: True
  handoff plumbing still in history:      True
  input tokens (gpt2 bpe): 574
```

The refund agent inherits the user turn, the triage agent's tool call, the 310-token order record, *and* the handoff machinery itself — the `transfer_to_refund_agent` call and its output `{"assistant": "Refund_agent"}`. The specialist can read the order. It can also read the fact that it was transferred, which is why the SDK ships a [`RECOMMENDED_PROMPT_PREFIX`](https://github.com/openai/openai-agents-python/blob/main/src/agents/extensions/handoff_prompt.py) telling the model that "Transfers between agents are handled seamlessly in the background; do not mention or draw attention to these transfers in your conversation with the user."

The SDK gives you two ways to change this. The first is an input filter, and the batteries-included one is `remove_all_tools`:

```
-- B. input_filter=remove_all_tools ---------------------------------------
input items handed to Refund_agent: 1
  [0] message role=user      Order A-1183 arrived damaged. I want a refund.
  order record reachable by Refund_agent: False
  handoff plumbing still in history:      False
  input tokens (gpt2 bpe): 25
```

574 tokens down to 25. The refund agent starts from the raw customer sentence with no idea an order lookup ever happened: a 96% reduction in context and a 100% reduction in what the triage agent learned.

The second is `nest_handoff_history`, an opt-in beta the docs describe as compacting "summarizable history into ordered assistant summary segments while preserving lossless message items in their original positions." Here is what it actually produced:

```
-- C. RunConfig(nest_handoff_history=True) --------------------------------
input items handed to Refund_agent: 1
  [0] message role=assistant For context, here is the conversation so far between the user and the previou…
  order record reachable by Refund_agent: True
  handoff plumbing still in history:      True
  input tokens (gpt2 bpe): 830
  --- verbatim content of item [0] ---
  | For context, here is the conversation so far between the user and the previous agent:
  | <CONVERSATION HISTORY>
  | 1. user: Order A-1183 arrived damaged. I want a refund.
  | 2. {"arguments": "{\"order_id\":\"A-1183\"}", "call_id": "call_lookup_1", "name": "lookup_order"
  | 3. {"call_id": "call_lookup_1", "output": "{\n  \"order_id\": \"A-1183\",\n  \"customer_id\": \"
  | 4. {"arguments": "{}", "call_id": "call_handoff_1", "name": "transfer_to_refund_agent", "type": 
  | 5. {"call_id": "call_handoff_1", "output": "{\"assistant\": \"Refund_agent\"}", "type": "functio
  | </CONVERSATION HISTORY>
```

Five structured items collapsed into one assistant message — and **830 tokens, up from 574**. "Compacts" in the documentation refers to message-list structure, not token count: nesting turns typed items into JSON strings embedded in a text block, and escaped JSON costs more than the structured items it replaced. On this transcript, 45% more.

### Microsoft Agent Framework: text only, no negotiation

The Agent Framework's `HandoffBuilder` reaches the opposite conclusion, and it does not expose a knob. Same scenario, same order record:

```
-- WHAT THE REFUND AGENT'S CLIENT SAW -------------------------------------
call 0: 2 messages
  [0] role=user                 contents=['text'] Order A-1183 arrived damaged. I want a refund.
  [1] role=assistant            author=triage contents=['text'] Damaged on delivery, sending to refunds.
  input tokens (gpt2 bpe): 122

-- VERDICT ----------------------------------------------------------------
  order record reachable by refund agent: False
  any function_call content present:      False
  any function_result content present:    False
  refund agent input tokens:              122
```

Two messages: the user's request and the triage agent's plain-text sentence, tagged `author=triage`. The tool call is gone, the tool result is gone, the order record is gone.

The stripping is not incidental. The same script applies the framework's own helper directly to the triage agent's last view of the conversation:

```
-- clean_conversation_for_handoff() APPLIED TO TRIAGE'S OWN VIEW ----------
  before: 3 messages, 1051 tokens
  after : 1 messages, 84 tokens
    [0] role=user                 contents=['text'] Order A-1183 arrived damaged. I want a refund.
```

Three messages and 1,051 tokens reduced to one message and 84. Everything the triage agent did is discarded before the next agent is allowed to see it.

### LangGraph: whatever the Command explicitly wrote

LangGraph has no handoff primitive. The documented pattern, in [LangChain's handoffs guide](https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/multi-agent/handoffs.mdx), is a tool that returns a `Command` with `goto` and `graph=Command.PARENT`. The receiving node then reads the shared `messages` channel.

The intuition most people carry into this is that the shared channel means shared history. I ran four variants to test it.

```
-- A. Command(PARENT) writing only the ToolMessage ------------------------
final shared channel: 3 messages
  [0] HumanMessage Order A-1183 arrived damaged. I want a refund.
  [1] ToolMessage  tool_call_id=call_handoff_1 Transferred to refund agent.
  [2] AIMessage    Refund of $248.50 approved for order A-1183.
  refund agent's model received 3 messages, 151 tokens
  order record reachable by refund agent: False
  triage's tool calls visible to refund:  False
  dangling tool_calls in final transcript: none
  orphan ToolMessages in final transcript: ['call_handoff_1']

-- B. Command(PARENT) writing nothing -------------------------------------
final shared channel: 2 messages
  [0] HumanMessage Order A-1183 arrived damaged. I want a refund.
  [1] AIMessage    Refund of $248.50 approved for order A-1183.
  refund agent's model received 2 messages, 81 tokens
  order record reachable by refund agent: False
  triage's tool calls visible to refund:  False
  dangling tool_calls in final transcript: none
  orphan ToolMessages in final transcript: none

-- C. Command(PARENT) writing AIMessage + ToolMessage (docs pattern) ------
final shared channel: 4 messages
  [0] HumanMessage Order A-1183 arrived damaged. I want a refund.
  [1] AIMessage    tool_calls=transfer_to_refund 
  [2] ToolMessage  tool_call_id=call_handoff_1 Transferred to refund agent.
  [3] AIMessage    Refund of $248.50 approved for order A-1183.
  refund agent's model received 4 messages, 233 tokens
  order record reachable by refund agent: False
  triage's tool calls visible to refund:  False
  dangling tool_calls in final transcript: none
  orphan ToolMessages in final transcript: none

-- D. CONTROL: plain tool result, triage node runs to completion ----------
final shared channel: 7 messages
  [0] HumanMessage Order A-1183 arrived damaged. I want a refund.
  [1] AIMessage    tool_calls=lookup_order 
  [2] ToolMessage  tool_call_id=call_lookup_1 { "order_id": "A-1183", "customer_id": "C-90422", "plac…
  [3] AIMessage    tool_calls=transfer_to_refund 
  [4] ToolMessage  tool_call_id=call_handoff_1 Transferred to refund agent.
  [5] AIMessage    Routing to refunds.
  [6] AIMessage    Refund of $248.50 approved for order A-1183.
  refund agent's model received 7 messages, 840 tokens
  order record reachable by refund agent: True
  triage's tool calls visible to refund:  True
  dangling tool_calls in final transcript: none
  orphan ToolMessages in final transcript: none
```

Each variant prints two lists, and they are not the same list. "Final shared channel" is the parent graph's `messages` after the run; "refund agent's model received" is that agent's model input, which adds its own `SystemMessage` and stops before the agent's reply. Their equal counts are coincidence.

Variants A, B and C all use `Command(graph=Command.PARENT)`. In every one, the triage agent's `lookup_order` call and the 310-token order record never reached the parent channel. The receiving agent got between 81 and 233 tokens — 37 of them the system prompt — and in no case could it read the order.

Variant D is the control. It changes two things that cannot be separated — the handoff tool returns an ordinary string instead of a `Command`, and a static edge does the routing `goto` was doing — so read it as "let the node finish" versus "short-circuit the node." The triage node now runs to completion, its whole transcript lands in the shared channel, and the refund agent's model receives 7 messages and 840 tokens with the order record intact.

The shared channel does share history. The `Command(graph=Command.PARENT)` short-circuit is what stops the sending node's writes from getting there.

LangChain's documentation considers this desirable, in a note titled "Why not pass all subagent messages?" — "The receiving agent may become confused by irrelevant internal reasoning, and token costs increase unnecessarily. By passing only the handoff pair, you keep the parent graph's context focused on high-level coordination." It recommends summarising the subagent's work into the `ToolMessage` content when the receiver needs more. A coherent position, and close to where the Agent Framework lands by force. The trap is not the design; it is that the design is easy to mistake for full history sharing, because the channel is shared and the word for the pattern is "handoff."

## Under the Hood

Three behaviours, three mechanisms. Reading the implementations explains why the defaults diverge.

### A handoff is a tool call that swaps the agent (OpenAI Agents SDK)

In the Agents SDK, a handoff is compiled into a function tool. [`Handoff.default_tool_name()`](https://github.com/openai/openai-agents-python/blob/main/src/agents/handoffs/__init__.py) builds `transfer_to_<agent_name>` in Python function style, which is why an agent named `Refund_agent` gets the tool `transfer_to_refund_agent`. The default description comes from `default_tool_description()`: "Handoff to the {agent.name} agent to handle the request."

When the model calls it, `on_invoke_handoff` returns the new agent and the runner swaps which agent owns the loop. Because it is a tool call resolved inside one run, the conversation stays a single continuous item list — hence the default that the next agent sees all of it. The `Handoff` dataclass says so in the `input_filter` field itself: "By default, the new agent sees the entire conversation history."

`nest_handoff_history` is the interesting one. [`agents/handoffs/history.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/handoffs/history.py) partitions the transcript rather than truncating it. Two predicates decide each item's fate. `_should_forward_pre_item` returns `False` for any item whose `role` is `assistant`, for items belonging to a hosted-program transcript, and for anything in `_SUMMARY_ONLY_INPUT_TYPES`, which is exactly:

```python
_SUMMARY_ONLY_INPUT_TYPES = {
    "function_call",
    "function_call_output",
    # Reasoning items can become orphaned after other summarized items are filtered.
    "reasoning",
}
```

Items that fail the predicate go into a pending summary buffer. Items that pass are forwarded verbatim. `_build_ordered_default_history` walks the transcript in order, flushing the buffer into a summary message whenever it hits a verbatim item, which is how "ordered summary segments preserving lossless items in their original positions" is implemented in practice.

The summary message itself is built by `_build_summary_message`, and its shape explains the token increase. Each buffered item becomes a numbered line. Items with a role and either no `content` or a newline-free string get the cheap legacy rendering, `role: content`. Everything else — every function call, every tool output — is rendered by `_format_transcript_item_json` as `json.dumps(payload)`. A tool result that was a structured `function_call_output` item becomes a JSON string nested inside another JSON string inside a text block, with every quote escaped. That is the 574-to-830 jump.

The receiving agent got *one* item rather than a user message plus a summary because the original run input lives in `input_history`, and `input_history` always goes into the summary buffer. Only `pre_handoff_items` and `new_items` are eligible for verbatim forwarding.

A comment on the legacy renderer shows how much of this format is about round-tripping rather than prose — summaries must survive being re-parsed and re-flattened on the *next* handoff:

```python
# Always emit the separator. A bare role has no record separator for the parser to
# find, so the turn is dropped when the summary is flattened on the next handoff.
```

Finally, the opt-in is conditional. Per the docs, nesting "applies only when neither the handoff's `input_filter` nor the active run's `RunConfig.handoff_input_filter` is set." Set a filter and your `nest_handoff_history=True` silently does nothing. And [`run_config.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/run_config.py) confirms the default is off:

```python
nest_handoff_history: bool = False
```

### A handoff is a broadcast of cleaned text (Microsoft Agent Framework)

The Agent Framework routes handoffs through a workflow executor. Every agent response passes through [`clean_conversation_for_handoff`](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_orchestrator_helpers.py) before it is added to the shared conversation or broadcast to other participants. The docstring states the reasoning directly:

> Handoff executors must not replay prior tool-control artifacts (function calls, tool outputs, approval payloads) into future model turns, or providers may reject the next request due to unmatched tool-call state.

The implementation is blunt: keep `content.type == "text"` parts, drop the message entirely if nothing remains, preserve role and `author_name`. There is even a `TODO` in the source acknowledging the bluntness — "This is a simplified check that considers any non-text content as a tool call."

In [`_handoff.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_handoff.py) the call site takes no opt-out: every completed agent response goes through it, the only earlier exit being an agent still waiting on the user. The comment explains the second motivation:

```python
# Remove function call related content from the agent response for full conversation history
cleaned_response = clean_conversation_for_handoff(response.messages)
```

with the surrounding note that this "removes function call related content such that the result stays consistent regardless of which agent yields Workflow Output." Reproducible workflow output is being bought with the specialist's context.

The handoff tool itself is created by `_create_handoff_tool`, named `handoff_to_<target_id>` by `get_handoff_tool_name`. It is intercepted by `_AutoHandoffMiddleware`, a `FunctionMiddleware` that never lets the tool body execute: it sets a synthetic result and raises `MiddlewareTermination`. That is how the framework short-circuits the agent's tool loop the instant a transfer is requested, and it is also why the executor immediately appends the synthetic handoff message to its cache — the source comment is explicit that "each tool call must have a corresponding tool result."

The framework also refuses to build a handoff workflow unless every participant opts into strict history persistence — `build()` raises unless each agent sets `require_per_service_call_history_persistence=True`, "to ensure local history stays consistent with the service across handoff tool-call short-circuits." Short-circuiting a tool loop is exactly what desynchronises local history from a provider-managed thread, and the framework makes you acknowledge it.

### A handoff is a graph edge with a payload (LangGraph)

[`Command`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/types.py) is documented as "one or more commands to update the graph's state and send messages to nodes," where `graph=Command.PARENT` targets "closest parent graph" and `update` is the "update to apply to the graph's state."

That is the whole mechanism, and it explains the measurement. When a tool inside the triage subgraph returns `Command(goto="refund", graph=Command.PARENT, update={...})`, the parent receives `goto` and `update`, and the subgraph never finishes and returns its accumulated state. Whatever the triage agent wrote into its own `messages` — the `lookup_order` call, the 310-token result, the AIMessage requesting the transfer — does not propagate. The `update` dict is the entire payload.

Which is why the LangChain documentation's handoff tool looks the way it does:

```python
last_ai_message = next(
    msg for msg in reversed(runtime.state["messages"]) if isinstance(msg, AIMessage)
)
transfer_message = ToolMessage(
    content="Transferred to sales agent",
    tool_call_id=runtime.tool_call_id,
)
return Command(
    goto="sales_agent",
    update={
        "active_agent": "sales_agent",
        "messages": [last_ai_message, transfer_message],
    },
    graph=Command.PARENT
)
```

Reaching back into `runtime.state` to fish out `last_ai_message` and hand-carry it into the update is not decoration; it is the fix for the defect variant A reproduced. The docs carry an explicit warning on this section: "Unlike single-agent middleware (where message history flows naturally), you must explicitly decide what messages pass between agents. Get this wrong and agents receive malformed conversation history or bloated context."

## Try It Yourself

Four scripts, no API keys, no network at runtime, no GPU.

```bash
python3 -m venv venv
./venv/bin/pip install \
  "openai-agents==0.22.0" \
  "langgraph==1.2.11" \
  "langchain-core==1.6.0" \
  "agent-framework-core==1.15.0" \
  "agent-framework-orchestrations==1.1.1" \
  blingfire numpy

# all four import common.py, which holds the shared scenario and the tokenizer
./venv/bin/python 01_openai_agents_handoff.py
./venv/bin/python 02_agent_framework_handoff.py
./venv/bin/python 03_langgraph_handoff.py
./venv/bin/python 04_delegation_vs_handoff.py
```

The core of experiment 1 is short, because the SDK does the recording for you:

```python
from agents import Agent, RunConfig, Runner, handoff
from agents.extensions.handoff_filters import remove_all_tools
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

model = ScriptedModel([
    ModelStep(output=[function_call(
        "lookup_order", {"order_id": "A-1183"}, call_id="call_lookup_1")]),
    ModelStep(output=[function_call(
        "transfer_to_refund_agent", {}, call_id="call_handoff_1")]),
    ModelStep(output=[assistant_message(
        "Refund of $248.50 approved for order A-1183.")]),
])
refund = Agent(name="Refund_agent", instructions="You process refunds.", model=model)
triage = Agent(
    name="Triage_agent", instructions="You triage support requests.", model=model,
    tools=[lookup_order],
    handoffs=[refund],   # or handoff(refund, input_filter=remove_all_tools)
)
await Runner.run(triage, USER_REQUEST,
                 run_config=RunConfig(nest_handoff_history=False))

# calls[2] is the first call made *after* the handoff: the refund agent.
receiving_call = model.calls[2]
```

`receiving_call.input` is the list printed in the outputs above.

Experiment 4 puts the whole-run cost of every option side by side, including a fourth architecture I have not discussed yet:

```
-- WHOLE-RUN COST, ONE IDENTICAL TASK -------------------------------------
architecture                        calls   in-tok  sub sees
handoff, default                        3     1093      True   owner after: Refund_agent
handoff, remove_all_tools               3      544     False   owner after: Refund_agent
handoff, nest_handoff_history           3     1349      True   owner after: Refund_agent
as_tool() delegation                    4     1155     False   owner after: Triage_agent

-- WHAT THE DELEGATED AGENT RECEIVED --------------------------------------
  [0] role=user Approve a damaged-goods refund for order A-1183, total $248.50.
  sub-agent input tokens: 34
  caller's own calls: 3, caller input tokens: 1121

'sub sees' = whether the second agent could read the order record
'in-tok'   = input tokens summed over every model call in the run
```

### The fourth option: delegate instead of transfer

`Agent.as_tool()` wraps an agent as a function tool. The SDK's own docstring names the two differences precisely:

> 1. In handoffs, the new agent receives the conversation history. In this tool, the new agent receives generated input.
> 2. In handoffs, the new agent takes over the conversation. In this tool, the new agent is called as a tool, and the conversation is continued by the original agent.

Both show up in the measurement. The delegated refund agent received a single user message of 34 tokens — a sentence the triage model wrote — and the `owner after` column shows `Triage_agent` still holding the loop, where every handoff variant shows `Refund_agent`.

The cost profile is easy to misread. Delegation looks cheap because the sub-agent's context is tiny, but the caller pays for the round trip: the triage agent makes three calls totalling 1,121 tokens, because the sub-agent's answer returns as a tool result the caller must reason over. Total 1,155 tokens across four calls, slightly more than the 1,093 of a full-history handoff. The margin is small and the two scripts are not identical, so read it as "delegation did not save tokens here," not as a general penalty. The reliable difference is control flow: the caller stays in charge and the specialist stays sandboxed.

## Where This Breaks / Tradeoffs

### The orphan tool message is one forgotten line away

Variant A of the LangGraph experiment produced a parent transcript containing a `ToolMessage` with `tool_call_id=call_handoff_1` and no `AIMessage` anywhere requesting that call. My checker flagged it:

```
  orphan ToolMessages in final transcript: ['call_handoff_1']
```

Providers validate tool-call pairing in both directions: a call with no result and a result with no call are both rejectable. The LangChain docs are direct about the first — "The `ToolMessage` with matching `tool_call_id` completes this request-response cycle—without it, the conversation history becomes malformed." Variant A gets that half right and still produces an invalid transcript, because in a `Command(graph=Command.PARENT)` handoff the AIMessage carrying the call never reaches the parent either. You need both, which is what variant C and the documented pattern do.

This is also the exact failure the Agent Framework's `clean_conversation_for_handoff` docstring cites as its reason for existing. Two frameworks, same hazard, opposite mitigations: LangGraph asks you to carry the pair forward by hand; the Agent Framework removes the possibility by deleting all tool traffic.

### "Compaction" that increases token count

`nest_handoff_history` reduced five items to one and raised the token count from 574 to 830, and the whole-run total from 1,093 to 1,349. If you enable it expecting a cost reduction, you will get the opposite on tool-heavy transcripts, because escaped JSON inside a text block is a worse encoding than the structured items it replaces.

What it buys is real: one message instead of five means no tool-call pairing to get wrong at the boundary, and a `<CONVERSATION HISTORY>` envelope that survives repeated handoffs. Judge it as a correctness feature. It is also still a beta "disabled by default while we stabilize it."

### Silent capability loss

The `remove_all_tools` filter dropped the refund agent from 574 tokens to 25, and the order record with it. The Agent Framework does the equivalent unconditionally. In both cases the specialist is told a customer wants a refund and is given nothing else.

If the specialist has its own `lookup_order` tool, the cost is one duplicated call: slow, but self-correcting. If it does not, the model will either ask the customer something the system already knows or invent an answer. Aggressive filtering does not raise; it quietly moves work back onto the model.

The Agent Framework's stripping is also coarser than it looks: `clean_conversation_for_handoff` drops any message whose remaining text is empty, so an assistant turn that was purely a tool call disappears entirely — and its own `TODO` admits the check treats all non-text content as tool-related.

### The whole-conversation cost grows with every hop

The numbers above are for one handoff. Full-history handoff means every subsequent agent pays for everything every previous agent did, so two hops with a tool-heavy first agent leave the third agent's prompt carrying both prior transcripts. The LangChain docs list this under implementation considerations: "Balance context completeness against token costs. Summarization and selective context passing become more important as conversations grow longer."

There is a second-order effect. In the SDK's default mode the receiving agent can see the `transfer_to_refund_agent` call in its own history, which is why the recommended prompt prefix exists to tell the model not to mention transfers — prompt tokens on every call, spent to paper over a context-transfer decision.

### Layer order will bite you when you write a fake client

To test the Agent Framework end to end I needed a chat client that supports function invocation. Composing the layers as `ChatMiddlewareLayer, FunctionInvocationLayer, ChatTelemetryLayer, BaseChatClient` looked right and produced a client that ran, but logged:

```
Ignoring unrecognized middleware of type _AutoHandoffMiddleware: it is neither a ChatMiddleware nor a callable and will not be executed.
```

The handoff never fired; the triage agent just looped. `FunctionInvocationLayer.__init__` categorises incoming middleware and forwards only the chat half to `super().__init__()`, so it has to sit *above* `ChatMiddlewareLayer` in the MRO. Reordering to `FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, BaseChatClient` fixed it. If you build test doubles against this framework, that ordering is load-bearing, and getting it wrong degrades to a warning rather than an error.

### What these experiments do not cover

Scripted models mean I measured the plumbing, not the behaviour. Whether a refund agent that cannot see the order record actually performs worse is a question for an eval with real models, and the answer will depend on your prompts and tools. What is settled here is what each framework transmits — the input to such an eval, not a substitute for it.

## Choosing between them

Each of these is one framework's default position on a design question you can override in all three, so the question is which position your system wants.

**Full history** suits a genuine conversation continuation, where the specialist picks up mid-thread. It costs the most and it exposes the transfer machinery to the model.

**Text-only** suits a routing topology where each specialist is self-sufficient. Cheap, structurally immune to tool-pairing bugs, and lossy in a way that stays invisible until a specialist asks for something the system already knew.

**Explicit payload**, the LangGraph position, is the most work and the most control, and the easiest to get subtly wrong — which is why the docs hand you a specific two-message recipe.

**Delegation** is often the right answer for a specialist that never talks to the user: a classifier, a policy check, a summariser. Just do not adopt it expecting a smaller bill.

Whichever you pick, do what produced this article: record what your second agent actually receives. It takes a handful of lines with a fake model, and the answer is frequently not what the architecture diagram implies.

## Key Takeaways

- The same triage-to-refund handoff delivered **574 tokens to the receiving agent in the OpenAI Agents SDK, 122 in Microsoft Agent Framework, and 233 in LangGraph's documented pattern**. Two of the three could not read the order record the first agent had just fetched. Read 122 against 233 as directional only — the frameworks serialize the same sentence at 25, 59 and 46 tokens, and only LangGraph's count carries a 37-token system prompt. The robust finding is which framework forwarded the 310-token order record.
- The OpenAI Agents SDK forwards **everything** by default, including the `transfer_to_*` call and its output. Microsoft's `HandoffBuilder` strips **all** non-text content unconditionally via `clean_conversation_for_handoff`. Opposite defaults, both documented, neither configurable in the same way.
- `Command(goto=..., graph=Command.PARENT)` in LangGraph discards the sending node's accumulated state. The control that let the node finish normally shared 840 tokens; every `Command` variant shared 233 or fewer. The shared channel is not the mechanism that gets history across — the node's return is.
- `nest_handoff_history=True` **raised** token count from 574 to 830 on a tool-heavy transcript. It is a transcript-hygiene feature, not a cost feature, and it is off by default and skipped entirely if any input filter is set.
- Omitting the AIMessage from a LangGraph handoff `Command` produces an orphan `ToolMessage` in the parent transcript — the mirror image of a dangling tool call, and equally rejectable. The documented pattern re-injects `last_ai_message` for exactly this reason.
- `Agent.as_tool()` delegation gave the sub-agent 34 tokens and left the caller owning the loop, but cost **1,155 tokens across the run versus 1,093** for a full-history handoff. Choose it for control flow, not for cost.

## Sources

All read in full on 2026-08-23. Package release dates from the PyPI JSON API.

1. [OpenAI Agents SDK — `docs/handoffs.md`](https://github.com/openai/openai-agents-python/blob/main/docs/handoffs.md), openai/openai-agents-python, main branch — default full-history behaviour, `input_filter`, `nest_handoff_history` beta semantics and `<CONVERSATION HISTORY>` wrapper.
2. [OpenAI Agents SDK — `src/agents/handoffs/history.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/handoffs/history.py) and [`src/agents/handoffs/__init__.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/handoffs/__init__.py), as shipped in `openai-agents==0.22.0`, released 2026-08-19 — `_SUMMARY_ONLY_INPUT_TYPES`, `_build_ordered_default_history`, `_build_summary_message`, `default_tool_name`.
3. [OpenAI Agents SDK — `src/agents/extensions/handoff_filters.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/extensions/handoff_filters.py), [`src/agents/run_config.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/run_config.py) and [`src/agents/extensions/handoff_prompt.py`](https://github.com/openai/openai-agents-python/blob/main/src/agents/extensions/handoff_prompt.py), `openai-agents==0.22.0`, 2026-08-19 — `remove_all_tools`, `nest_handoff_history: bool = False`, and the verbatim `RECOMMENDED_PROMPT_PREFIX`.
4. [Microsoft Agent Framework — `_orchestrator_helpers.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_orchestrator_helpers.py), as shipped in `agent-framework-orchestrations==1.1.1`, released 2026-08-21 — `clean_conversation_for_handoff` and its stated rationale.
5. [Microsoft Agent Framework — `_handoff.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_handoff.py), `agent-framework-orchestrations==1.1.1`, 2026-08-21 — `HandoffBuilder`, `get_handoff_tool_name`, `_AutoHandoffMiddleware`, the unconditional cleaning call site, and the `require_per_service_call_history_persistence` build check.
6. [LangChain docs — `src/oss/langchain/multi-agent/handoffs.mdx`](https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/multi-agent/handoffs.mdx), langchain-ai/docs, main branch — the `Command.PARENT` handoff tool with `last_ai_message`, the ToolMessage pairing note, the subgraph context-engineering warning, and the implementation considerations.
7. [LangGraph — `libs/langgraph/langgraph/types.py`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/types.py), as shipped in `langgraph==1.2.11`, released 2026-08-11 — the `Command` contract for `graph`, `goto` and `update`.
8. [OpenAI Agents SDK — `agents.testing.ScriptedModel`](https://github.com/openai/openai-agents-python/blob/main/src/agents/testing/model.py) and the `Agent.as_tool()` docstring, `openai-agents==0.22.0`, 2026-08-19 — the recording harness and the stated handoff-versus-delegation distinction.
9. PyPI JSON API release metadata, retrieved 2026-08-23: [openai-agents 0.22.0](https://pypi.org/project/openai-agents/0.22.0/) (2026-08-19), [agent-framework-core 1.15.0](https://pypi.org/project/agent-framework-core/1.15.0/) (2026-08-21), [agent-framework-orchestrations 1.1.1](https://pypi.org/project/agent-framework-orchestrations/1.1.1/) (2026-08-21), [langgraph 1.2.11](https://pypi.org/project/langgraph/1.2.11/) (2026-08-11), [langchain-core 1.6.0](https://pypi.org/project/langchain-core/1.6.0/) (2026-08-19).
