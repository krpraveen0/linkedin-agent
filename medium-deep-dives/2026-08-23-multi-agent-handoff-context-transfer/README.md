# What the second agent actually sees when the first one hands off

Runnable code for the deep-dive article [`article.md`](./article.md).

One identical scenario - a triage agent looks up a 310-token order record, then
transfers to a refund agent - built four ways across three frameworks, with the
exact request handed to the *receiving* agent recorded and measured.

Every model here is a scripted test double. **No API keys, no network at
runtime, no GPU.** All four scripts are deterministic: running one twice gives
byte-identical output.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install \
  "openai-agents==0.22.0" \
  "langgraph==1.2.11" \
  "langchain-core==1.6.0" \
  "agent-framework-core==1.15.0" \
  "agent-framework-orchestrations==1.1.1" \
  blingfire numpy
```

Python 3.11.15 was used. Exact versions that produced every number below:

```
agent-framework-core           1.15.0
agent-framework-orchestrations 1.1.1
blingfire                      0.1.8
langchain-core                 1.6.0
langgraph                      1.2.11
langgraph-checkpoint           4.2.0
langgraph-prebuilt             1.1.0
numpy                          2.4.6
openai                         3.3.1
openai-agents                  0.22.0
pydantic                       2.13.4
```

`blingfire` supplies the tokenizer. It ships the GPT-2 BPE model *inside the
wheel*, so token counts need no network access. It is a consistent yardstick,
not a billing estimate for any current production model.

## Files

| File | What it does |
|---|---|
| `common.py` | The shared scenario, the offline tokenizer, and `strip_volatile()` which removes per-run message UUIDs so counts are stable |
| `01_openai_agents_handoff.py` | OpenAI Agents SDK under three settings: default, `remove_all_tools`, `nest_handoff_history=True` |
| `02_agent_framework_handoff.py` | Microsoft Agent Framework `HandoffBuilder`, plus `clean_conversation_for_handoff()` applied directly |
| `03_langgraph_handoff.py` | LangGraph `Command(goto, graph=PARENT)` in four variants, including the documented pattern and a control |
| `04_delegation_vs_handoff.py` | Whole-run cost of every handoff variant against `Agent.as_tool()` delegation |
| `figure1-three-mechanisms.svg` | The three transfer mechanisms side by side |
| `figure2-nest-history-internals.svg` | How `nest_handoff_history` partitions a transcript |
| `figure3-tool-pairing-failures.svg` | Dangling tool call vs orphan tool result, and each framework's mitigation |

## Run

```bash
./venv/bin/python -W ignore 01_openai_agents_handoff.py
./venv/bin/python -W ignore 02_agent_framework_handoff.py
./venv/bin/python -W ignore 03_langgraph_handoff.py
./venv/bin/python -W ignore 04_delegation_vs_handoff.py
```

`-W ignore` only silences a `create_react_agent` deprecation notice from
LangGraph 1.x; the scripts run fine without it.

## Real captured output

### 1. OpenAI Agents SDK

```
-- SCENARIO ---------------------------------------------------------------
user: Order A-1183 arrived damaged. I want a refund.
tool result (lookup_order) is 310 tokens of JSON

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

-- B. input_filter=remove_all_tools ---------------------------------------
input items handed to Refund_agent: 1
  [0] message role=user      Order A-1183 arrived damaged. I want a refund.
  order record reachable by Refund_agent: False
  handoff plumbing still in history:      False
  input tokens (gpt2 bpe): 25

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

-- SUMMARY ----------------------------------------------------------------
config                      items   tokens
A default                       5      574
B remove_all_tools              1       25
C nest_handoff_history          1      830
OPENAI_API_KEY is not set, skipping trace export
```

### 2. Microsoft Agent Framework

```
-- SCENARIO ---------------------------------------------------------------
user: Order A-1183 arrived damaged. I want a refund.
lookup_order returns 310 tokens of JSON

No handoff configuration found for agent 'refund'. This agent will not be able to hand off to any other agents and your workflow may get stuck.
-- WHAT THE TRIAGE AGENT'S CLIENT SAW -------------------------------------
call 0: 1 messages
  [0] role=user                 contents=['text'] Order A-1183 arrived damaged. I want a refund.
  input tokens (gpt2 bpe): 59

call 1: 3 messages
  [0] role=user                 contents=['text'] Order A-1183 arrived damaged. I want a refund.
  [1] role=assistant            contents=['function_call'] 
  [2] role=tool                 contents=['function_result'] 
  input tokens (gpt2 bpe): 1051

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

-- clean_conversation_for_handoff() APPLIED TO TRIAGE'S OWN VIEW ----------
  before: 3 messages, 1051 tokens
  after : 1 messages, 84 tokens
    [0] role=user                 contents=['text'] Order A-1183 arrived damaged. I want a refund.
```

The `No handoff configuration found for agent 'refund'` line is expected: the
refund agent is a leaf with no outgoing handoffs.

### 3. LangGraph

```
-- SCENARIO ---------------------------------------------------------------
user: Order A-1183 arrived damaged. I want a refund.
lookup_order returns 310 tokens of JSON

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

### 4. Delegation vs handoff

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
OPENAI_API_KEY is not set, skipping trace export
```

## The short version

| Architecture | Receiving agent gets | Can it read the order record? |
|---|---|---|
| OpenAI Agents SDK, default | 5 items, 574 tokens | yes |
| OpenAI Agents SDK, `remove_all_tools` | 1 item, 25 tokens | no |
| OpenAI Agents SDK, `nest_handoff_history` | 1 item, 830 tokens | yes |
| Microsoft Agent Framework `HandoffBuilder` | 2 messages, 122 tokens | no |
| LangGraph `Command(PARENT)`, docs pattern | 4 messages, 233 tokens | no |
| LangGraph control (node runs to completion) | 7 messages, 840 tokens | yes |
| `Agent.as_tool()` delegation | 1 message, 34 tokens | no |

## A note on the fake Agent Framework client

`02_agent_framework_handoff.py` composes its recording client as
`FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, BaseChatClient`.
That order is load-bearing. Put `ChatMiddlewareLayer` first and the framework's
`_AutoHandoffMiddleware` is silently discarded with a warning, the tool loop is
never short-circuited, and the handoff never fires.
