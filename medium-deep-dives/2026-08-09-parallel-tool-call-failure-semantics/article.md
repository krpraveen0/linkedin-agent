# One Tool in the Batch Raised. I Checked What LangGraph, the OpenAI Agents SDK, and Pydantic AI Did With the Others.

Your model emits five tool calls in a single turn. Four of them succeed. The fifth raises a `ValueError` because a payment gateway timed out.

What should happen to the other four?

There is no obvious right answer, and the three most widely used Python agent frameworks have each landed somewhere different. One of them throws away all five results and lets the exception escape. One of them cancels the survivors on purpose and drains them before raising a wrapped error. One of them keeps whatever finished, then manufactures a placeholder result for the one that never did, so the conversation is still legal on the next request.

Those are not stylistic differences. They decide whether your agent's stored conversation is still something a provider will accept. Get it wrong and the failure does not show up at the moment of the error. It shows up on the *next* turn, as a 400, forever, on a session that can never make progress again.

I installed all three, ran the same failing batch through each of them, and captured what actually landed in the message history. This piece is what I found, why each framework chose what it chose, and what to do about it in your own code.

## The contract nobody writes down

Start with the rule that makes this matter, because it is enforced by the provider and not by your framework.

Every tool call in an assistant message must be answered. If an assistant message contains `tool_calls`, the messages that follow must include one tool result per `tool_call_id`, before the next assistant turn. A call with no matching result is an *orphan*, and an orphan is not a warning. It is a hard rejection.

OpenAI's Chat Completions wording, quoted in [an Agno bug report from 27 August 2025](https://github.com/agno-agi/agno/issues/4345):

> An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'. The following tool_call_ids did not have response messages: call_TdBqXQ0BT3C4qpUByCAuXqht

The Responses API rejects the same shape with different words. From [issue #673 on the OpenAI Agents SDK, opened 10 May 2025](https://github.com/openai/openai-agents-python/issues/673):

> Error code: 400 - {'error': {'message': 'No tool output found for function call call_***.', 'type': 'invalid_request_error', 'param': 'input', 'code': None}}

Now notice what makes this class of bug so unpleasant. Conversation history is append-only and persistent. If a crash writes an orphan into your session, every subsequent request replays that orphan. The session does not degrade. It bricks. The Pydantic AI source states the constraint plainly in a docstring: "Providers reject histories with dangling tool calls."

This is not theoretical, and it is not rare. In [issue #3084 on the `pi` agent runtime, filed 13 April 2026](https://github.com/earendil-works/pi/issues/3084), an agent issued 10 to 13 parallel tool calls, all of which executed successfully, and only 3 to 4 results were written to the session. No tool failed there. What threw was an `afterToolCall` hook during finalization, inside a `for...of` loop that awaited results sequentially, so the loop exited and abandoned every result it had not yet processed. The reported symptom was not a wrong answer. It was permanent session deadlock and 600-second timeouts. The recommended workaround was to turn parallel tool calling off entirely.

So: parallelism plus partial failure plus persistent history equals a corrupted session. Every framework has to answer this, and they answer it differently.

## The test

The setup is deliberately boring, because the interesting part is the plumbing, not the scenario.

One assistant turn requests two tools at once:

- `lookup_user`, which sleeps 50ms and returns successfully
- `charge_card`, which raises `ValueError("gateway timeout")` immediately

Two tool calls, `call_a` and `call_b`. One fast success, one instant failure. For each framework I record three things: what the framework returned or raised, what ended up in the persisted history, and whether the sibling's tool body actually ran to completion. That third one matters more than it looks, and I will come back to it.

I also check each resulting history for orphans, so "would a provider accept this?" gets a yes or no rather than a shrug.

Versions, all current at the time of writing and all installed from PyPI:

```
langgraph==1.2.10            (2026-07-28)
langgraph-prebuilt==1.1.0    (2026-05-12)
langchain-core==1.5.3        (2026-07-30)
openai-agents==0.19.4        (2026-08-05)
pydantic-ai-slim==2.27.0     (2026-08-08)
```

Everything runs against scripted fake models. No API keys, no network, no GPU.

## LangGraph: the whole node, or nothing

LangGraph's `ToolNode` runs a batch of tool calls concurrently and returns a list of `ToolMessage`s. The async path is one line, and that line is the whole story:

```python
outputs = await asyncio.gather(*coros)
```

There is no `return_exceptions=True`. `asyncio.gather` in its default mode propagates the first exception to the caller immediately, and the results of the other coroutines are discarded. Not "returned with an error marker". Discarded. The `_combine_tool_outputs` call on the next line never runs, so `ToolNode` produces zero messages rather than one-per-call.

Whether that exception ever reaches `gather` depends on `handle_tool_errors`, and this is where LangGraph changed in a way that caught people out. The default is not `True`. It is a function:

```python
def _default_handle_tool_errors(e: Exception) -> str:
    """Default error handler for tool errors.

    If the tool is a tool invocation error, return its message.
    Otherwise, raise the error.
    """
    if isinstance(e, ToolInvocationError):
        return e.message
    raise e
```

`ToolInvocationError` covers malformed arguments from the model, which is a recoverable thing worth telling the model about. Anything your tool body raises, including `ToolException`, is re-raised. [LangGraph issue #6486, "Tool node error handling disabled by default after 1.0.1"](https://github.com/langchain-ai/langgraph/issues/6486), opened 22 November 2025, reports exactly this transition, and [LangChain issue #33348, from 8 October 2025](https://github.com/langchain-ai/langchain/issues/33348), notes the knock-on effect that `create_agent` hardcodes `ToolNode(tools=available_tools)` with no way to configure it: "Any ToolException is re-raised and crashes agent.invoke()".

Running the batch through a compiled graph with an in-memory checkpointer, so I can read what actually got persisted:

```
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
```

Two things deserve attention.

First, under the default, the checkpoint holds one message: the assistant turn with both tool calls and no results at all. `call_a` succeeded and its result is gone. Both IDs are orphaned. This checkpoint is now permanently unsendable, and it is the checkpoint your resume logic will load.

Second, look at the last line of the first block. The sibling did not stop. `lookup_user` finished *after* the graph had already raised and returned, during a later phase of the program. The exception escaping `gather` unblocked the caller, but it did not cancel the pending task. The tool body kept running on the event loop, completed its work, and had nowhere to put the result.

That is the part that should worry you. If `lookup_user` were `send_refund` or `create_ticket`, the side effect lands. The record that it landed does not. Your agent will retry on the next turn, believing nothing happened.

## OpenAI Agents SDK: isolate first, then cancel deliberately

The Agents SDK takes the opposite starting position. Tool failures are, by default, not exceptional at all. They are content.

```python
def default_tool_error_function(ctx: RunContextWrapper[Any], error: Exception) -> str:
    """The default tool error function, which just returns a generic error message."""
    json_decode_error = _extract_tool_argument_json_error(error)
    if json_decode_error is not None:
        return (
            "An error occurred while parsing tool arguments. "
            "Please try again with valid JSON. "
            f"Error: {json_decode_error}"
        )
    return f"An error occurred while running the tool. Please try again. Error: {str(error)}"
```

Every `function_tool` gets this unless you say otherwise. An exception becomes a `function_call_output`, the model sees it, and the batch stays paired by construction. Running the same scenario, with the printout filtered to tool traffic (the two items not shown are the user message and the final assistant message, which is why the count says six):

```
--- default failure_error_function ---
  run completed: final_output='done'
  items in history: 6
    function_call        call_id='call_a' name='lookup_user'
    function_call        call_id='call_b' name='charge_card'
    function_call_output call_id='call_a' output='user u_1: ok'
    function_call_output call_id='call_b' output='An error occurred while running the tool. Please tr...'
  orphaned call_ids: none  -> provider would have accepted
```

The failure never becomes an exception, so there is nothing for a batch executor to unwind. Now switch it off with `failure_error_function=None`, which is what you do when you want a tool failure to abort the run rather than be narrated to the model:

```
--- failure_error_function=None ---
  run RAISED UserError: Error running tool charge_card: gateway timeout
  no RunResult was produced, so the caller has no history object to persist
  at the moment the run returned, completed tool bodies: ["lookup_user(u_1) CANCELLED during run='failure_error_function=None'"]
  after draining the event loop:  ["lookup_user(u_1) CANCELLED during run='failure_error_function=None'"]
```

Compare that last line to LangGraph's. The sibling did not keep running and quietly finish. It received `asyncio.CancelledError` and unwound. The SDK went and stopped it.

Note also that the error you catch is a wrapped `UserError`, not the `ValueError` your tool raised.

This behavior is four days old at the time of writing. [PR #4185, "fix(run): cancel sibling work after concurrent failures"](https://github.com/openai/openai-agents-python/pull/4185), shipped in v0.19.4 on 5 August 2026, and its stated goal is that "when one SDK-owned concurrent run operation fails, its sibling operations are cancelled and drained before the original error is propagated." The PR description notes it reuses existing cancellation and function-tool lifecycle machinery rather than adding public API, and that it preserves successful result ordering and streaming parity.

The word "drained" is doing real work there, and the source shows why.

## Under the Hood: three machines, three theories of the problem

### LangGraph optimises for a graph that fails loudly

`ToolNode` is a node in a graph, and LangGraph's position is that a node either produces its output or it fails. Partial output from a node is not a concept the runtime has. `asyncio.gather` without `return_exceptions` is the most direct expression of that: first error wins, everything else is dropped.

The sync path is the same shape with a different primitive:

```python
with get_executor_for_config(config) as executor:
    outputs = list(
        executor.map(self._run_one, tool_calls, input_types, tool_runtimes)
    )
```

`executor.map` is lazy, and `list()` raises as soon as it reaches a failed future. I did not test this path, but reading it, the sibling situation is if anything worse than the async one: `map` submits every callable to the thread pool immediately, so the siblings are not merely having their results discarded. They are running to completion in worker threads that nothing is waiting on.

The upside is that LangGraph gives you a checkpointer, so the crash is recoverable at the *graph* level: you resume from the last good checkpoint and re-run the node. The cost is that the checkpoint you resume from can contain an assistant turn whose tool calls have no results, and nothing in `ToolNode` reconciles that before the next model request goes out.

### The Agents SDK optimises for the batch as a unit of lifecycle

The Agents SDK does not run the function-tool batch through a bare `gather`. It has a `_FunctionToolBatchExecutor` that creates a task per call, tracks per-task state, enforces a concurrency ceiling, and collects results through `asyncio.wait(..., return_when=FIRST_COMPLETED)` in a loop, so a completed task can be recorded the moment it lands rather than at the end of the batch.

The decision of whether to isolate failures is made a layer up, in `tool_planning.py`, before the executor is even constructed:

```python
isolate_function_tool_failures = len(plan.function_runs) > 1 or (
    parallel
    and (
        bool(plan.computer_actions)
        or bool(plan.custom_tool_calls)
        or bool(plan.shell_calls)
        or bool(plan.apply_patch_calls)
        or bool(plan.local_shell_calls)
    )
)
```

Two function calls is the obvious trigger. The `or` clause is the interesting half: a *single* function tool also gets isolation when the same parallel turn contains a computer action, a custom tool call, a shell call, an apply-patch call, or a local-shell call. A lone function call still has siblings in that case, just in other categories, and orphaning does not care which category the unanswered call came from.

Worth flagging honestly, since it is the kind of thing a reader will check: the executor stores this value as `self.isolate_parallel_failures`, and in 0.19.4 nothing reads it back. Grepping the installed package finds the assignment and no consumer. The cancel-and-drain path is invoked unconditionally whenever a completed task reports a failure, so in this version the flag documents intent more than it gates behavior.

When a failure does propagate, the executor does not simply drop the pending tasks. It partitions them:

```python
def _partition_pending_tasks(self) -> tuple[set[asyncio.Task[Any]], set[asyncio.Task[Any]]]:
    cancellable_tasks = {
        task for task in self.pending_tasks if not self.task_states[task].in_post_invoke_phase
    }
    return cancellable_tasks, self.pending_tasks - cancellable_tasks
```

Tasks that have not yet reached their post-invoke phase are cancelled. Tasks that *have* are left alone and waited on, with a bounded timeout (`_FUNCTION_TOOL_POST_INVOKE_WAIT_SECONDS`), because a tool that has already produced its result and is running output guardrails or lifecycle hooks should be allowed to finish rather than be torn in half. Anything still outstanding after that gets a result callback attached so its exception is logged instead of surfacing as a stray "task exception was never retrieved."

There is also a separate path for the case where the parent itself is cancelled, distinct from the case where a sibling category failed. This is more machinery than most people expect behind "run some tools at once", and it exists because the naive version leaks.

### Pydantic AI optimises for the history being sendable

Pydantic AI accepts that runs get interrupted and fixes the artifact instead of the moment.

Two functions do the work. `_dangling_tool_calls_by_response` finds unanswered calls with a deliberately strict definition:

> Matching is an ordered walk: a tool result [...] only answers a call that is open (produced by an earlier response and not already answered) at that point. An out-of-place result — one preceding its call, a duplicate, or one reusing the ID of an already-answered call — doesn't mask a genuinely dangling call.

Then `_repair_dangling_tool_calls` synthesizes a result for each one, using a fixed placeholder:

```python
INTERRUPTED_TOOL_RETURN_CONTENT = 'The tool call was interrupted before a result was produced.'
```

The synthesized part carries `outcome='interrupted'` and a `SYNTHESIZED_TOOL_RETURN_METADATA_KEY` marker so you can tell manufactured results from real ones. Three properties in the docstring are worth calling out, because they are the difference between a repair and a hack:

The repair is **deterministic and idempotent**. Synthesized parts derive their timestamp from the response they repair and contain no wall-clock or random data, so "repairing the same history twice (or on every run) yields the same output and never churns provider prompt-cache prefixes." Repairing on every request would otherwise invalidate your cached prefix on every request.

It **never deletes**. A call whose arguments got cut off mid-stream as unparsable JSON is kept verbatim and closed out like any other dangling call, because removing it "would disturb the response's shape, e.g. leaving a thinking-only response whose signature was computed over a turn that included the call."

It is **frontier-gated**. The last `ModelResponse` is only repaired when `repair_last_response` is set, because those tool calls are still live: run resumption and `deferred_tool_results` may yet answer them.

Here is the whole thing end to end. Run 1 gets cancelled while `charge_card` is still sleeping. Run 2 hands the wreckage straight back to the agent:

```
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

Note what survived the cancellation: `call_a`'s real result. Pydantic AI captured the partial tool returns collected before the interruption rather than discarding the batch. Then, on the way out to the model, it closed the one genuine gap. The history that reaches the provider is complete, and the model is told, in words, that one of its tool calls never produced a result.

## Try it yourself

All four scripts run offline. Setup:

```bash
python3 -m venv venv && ./venv/bin/pip install \
  "langgraph==1.2.10" "langchain-core==1.5.3" \
  "pydantic-ai-slim==2.27.0" "openai-agents==0.19.4"
```

The LangGraph case, condensed to the part that matters:

```python
@tool
async def lookup_user(user_id: str) -> str:
    """Look up a user by id."""
    await asyncio.sleep(0.05)
    COMPLETED.append(f"lookup_user({user_id}) finished during run={CURRENT_RUN!r}")
    return f"user {user_id}: ok"

@tool
async def charge_card(amount: str) -> str:
    """Charge a card."""
    raise ValueError("gateway timeout")

graph = build(ToolNode([lookup_user, charge_card]))   # default error handling
await graph.ainvoke({"messages": [seed()]}, cfg)      # raises
# then read back what the checkpointer actually stored
describe((await graph.aget_state(cfg)).values["messages"])
```

The `CURRENT_RUN` tagging is the trick that exposes the leak. By recording *which phase of the program was active* when a tool body finished, rather than just that it finished, the output above shows `lookup_user` completing after its own graph invocation had already returned.

The fourth script is the practical one: a pairing check and repair over plain OpenAI-shaped message dicts, for stacks that do not do this for you.

```python
def find_orphans(messages: list[dict]) -> list[str]:
    """Return ids of tool_calls that never receive a matching tool message.

    Matching is an ordered walk: a tool message only answers a call that is
    already open and not yet answered at that point, so a duplicate or
    out-of-order result does not mask a genuinely dangling call.
    """
    open_calls: dict[str, int] = {}
    orphans: list[str] = []
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                open_calls[tc["id"]] = i
        elif m.get("role") == "tool":
            open_calls.pop(m.get("tool_call_id"), None)
    orphans.extend(open_calls)
    return orphans
```

Its full output on the two histories the earlier experiments produced:

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

That `repair is idempotent: True` is measuring this twenty-line function, not any framework's. It is checked because the pass runs before every request, and a repair that produced different bytes each time would invalidate your prompt cache on every turn. Pydantic AI's own repair claims the same property in its docstring, for the same reason.

## Where This Breaks / Tradeoffs

**Converting every exception into a tool result hides real bugs.** The Agents SDK default keeps your history valid, and it also means a typo in a tool body becomes a polite message to the model instead of a stack trace to you. The model then retries, fails again, and burns a loop. Failure isolation is an availability choice, and the cost is paid in observability. If you use it, alert on the error string, because the model will not.

**Cancelling siblings does not un-ring the bell.** The Agents SDK cancels pending tool tasks on sibling failure, but cancellation lands at the next `await`. A tool that already issued its HTTP POST and is waiting on the response gets cancelled after the write hit the server. The remote side effect happened; your process just stopped caring about the answer. Cancellation bounds resource waste. It does not give you transactionality, and nothing at this layer can.

**Synthesizing a result is a lie you are choosing to tell.** Pydantic AI's placeholder says the call was interrupted before producing a result. Sometimes that is false: the tool ran, did its work, and the process died before recording it. The model reads "interrupted", concludes nothing happened, and calls it again. For a read this is free. For `charge_card` it is a double charge. The synthesized marker is the hook you need here: on resume, check for `outcome='interrupted'` returns on non-idempotent tools and reconcile against the downstream system before letting the model act.

**LangGraph's strictness is defensible, and it is not the default people expect.** Failing the node loudly is the right call if you have a checkpointer, a retry policy, and reconciliation. What makes it sharp is the combination of a default that re-raises, a `create_agent` that does not expose the knob ([#33348](https://github.com/langchain-ai/langchain/issues/33348)), and siblings that keep running after the node has given up. The mitigation is a one-liner. `ToolNode(tools, handle_tool_errors=True)` pairs the batch, as the output above shows.

**None of this covers the process dying.** Every mechanism here is in-process. `SIGKILL` between a tool returning and its result being written leaves an orphan that only a repair pass at load time can fix. That is an argument for doing the pairing check when you *read* a session, not only when you write one.

**Parallelism is the thing that makes it expensive.** With one tool call per turn, a failure loses one result. With ten, a first-error-wins policy can discard nine successful results and their side effects, which is what [#3084](https://github.com/earendil-works/pi/issues/3084) reported. The workaround there was to disable parallel tool calls, and if you cannot audit your framework's batch semantics, that remains a legitimate, if slow, answer.

## What to do on Monday

Run the pairing check on every history you load and every history you send. It is twenty lines and it converts a permanently bricked session into a recoverable one.

Then decide, per tool, which of the three postures you want, because the framework default is a blanket policy and your tools are not all the same. Reads should almost always narrate their failures to the model and keep the batch intact. Writes should fail loudly and be reconciled explicitly. Pydantic AI lets you distinguish the two after the fact via `outcome`; the Agents SDK lets you set `failure_error_function` per tool; LangGraph lets you pass a callable or an exception tuple to `handle_tool_errors` so recoverable types are narrated and the rest are raised.

Finally, log the gap. Every framework here can leave you with work that happened and a result that did not get recorded. Only you know which of your tools that is dangerous for.

## Key Takeaways

- A tool call with no matching result is rejected by the provider, and because history is persistent, one orphan can brick a session permanently rather than fail once.
- LangGraph's `ToolNode` uses `asyncio.gather` with no `return_exceptions`, so one raising tool discards every sibling result. Its default handler re-raises anything that is not a `ToolInvocationError`. `handle_tool_errors=True` restores pairing.
- Abandoned siblings in LangGraph are not cancelled. They keep running and complete after the node has raised, so side effects land with no record.
- The OpenAI Agents SDK converts tool exceptions into tool outputs by default, which keeps batches paired. When you disable that, it cancels pending siblings, drains them, and raises a wrapped `UserError` (PR #4185, v0.19.4, 5 August 2026). Its isolation predicate covers a single function call sharing a turn with other tool categories, not only batches larger than one.
- Pydantic AI repairs the artifact instead: it keeps whatever results completed and synthesizes an `outcome='interrupted'` return for each dangling call. Its docstring states the repair is deterministic and idempotent so prompt-cache prefixes survive being repaired on every request.
- Cancellation is not rollback and a synthesized result is not the truth. Both buy you a legal history; neither tells you whether a side effect landed. Reconcile non-idempotent tools yourself.

## Sources

1. [langgraph-prebuilt 1.1.0 on PyPI](https://pypi.org/project/langgraph-prebuilt/) — released 12 May 2026. All line references are to `langgraph/prebuilt/tool_node.py` **as installed from that release**; the [copy on `main`](https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py) contains the same code at different line numbers.
2. [LangGraph issue #6486, "Tool node error handling disabled by default after 1.0.1"](https://github.com/langchain-ai/langgraph/issues/6486) — 22 November 2025.
3. [LangChain issue #33348, "`create_agent` doesn't allow configuring `ToolNode` error handling"](https://github.com/langchain-ai/langchain/issues/33348) — 8 October 2025.
4. [openai-agents 0.19.4 on PyPI](https://pypi.org/project/openai-agents/) — released 5 August 2026; `agents/run_internal/tool_execution.py`, `agents/run_internal/tool_planning.py` and `agents/tool.py` read as installed.
5. [OpenAI Agents SDK PR #4185, "fix(run): cancel sibling work after concurrent failures"](https://github.com/openai/openai-agents-python/pull/4185) — 5 August 2026.
6. [pydantic-ai-slim 2.27.0 on PyPI](https://pypi.org/project/pydantic-ai-slim/) — released 8 August 2026; `pydantic_ai/_agent_graph.py` and `pydantic_ai/messages.py` read as installed.
7. [`pi` issue #3084, "executeToolCallsParallel loses tool results when afterToolCall hook throws"](https://github.com/earendil-works/pi/issues/3084) — 13 April 2026.
8. [Agno issue #4345, OpenAI 400 on unmatched `tool_call_id`](https://github.com/agno-agi/agno/issues/4345) — 27 August 2025.
9. [OpenAI Agents SDK issue #673, "No tool output found for function call"](https://github.com/openai/openai-agents-python/issues/673) — 10 May 2025.
