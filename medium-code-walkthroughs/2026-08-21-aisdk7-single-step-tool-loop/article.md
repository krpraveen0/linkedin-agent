# I Asked My AI SDK Agent for the Weather. It Fetched It, Then Handed Back an Empty String.

I wired up a weather tool, called `generateText`, and asked a simple question: "What is the weather in Paris?" The model asked for the tool. The tool ran and returned `{ city: 'Paris', tempC: 21, sky: 'clear' }`. And then the whole call finished with `finishReason: 'tool-calls'` and `text: ""`.

No answer. The data was right there, fetched and sitting in the result object, and the agent said nothing about it.

This is not a bug. It is the single most common misunderstanding about how the [Vercel AI SDK](https://www.npmjs.com/package/ai) runs tools, and in AI SDK 7 the behavior is unchanged from 5 and 6: the low-level text functions run exactly one model step unless you tell them otherwise. Here is precisely what happens, why it happens, and the two ways to get your answer back.

## One call, one step

`generateText` and `streamText` are single-turn primitives. Each call sends your messages to the model, collects whatever the model produces, runs any tools the model asked for, and returns. That is one step. If the model's move in that step was "call the weather tool," then the step ends the moment the tool finishes. The SDK does not automatically send the tool's result back to the model for a second opinion.

So the sequence for my Paris question was:

1. Send the prompt and the tool definition to the model.
2. Model responds with a tool call, not text.
3. SDK executes the tool. `execute` runs, returns the weather object.
4. Step over. Return.

The model was invoked once. It never saw the tool's output, because seeing the output would require a second model call, and a second model call is a second step. `finishReason` is `'tool-calls'` — the honest signal that the run ended on a pending tool call, not on a finished thought. The tool result is in `result.steps[0]`, but `result.text` is empty because the model never wrote any text.

## `stopWhen` is the loop

To turn the primitive into an agent that keeps going, you pass `stopWhen`. It is a stopping condition, evaluated after each step. As long as the condition is not met and the last step contained tool calls, the SDK feeds the tool results back to the model and runs another step.

```ts
import { generateText, isStepCount } from 'ai';

const result = await generateText({
  model,
  tools: { weather },
  prompt: 'What is the weather in Paris?',
  stopWhen: isStepCount(5), // allow up to 5 steps
});
```

Now the run does what I originally expected: step 1 calls the tool, the SDK sends the result back, step 2 lets the model read it and write "It is 21C and clear in Paris," and the condition (`isStepCount(5)`) is still satisfied so it stops cleanly with `finishReason: 'stop'`.

A word on that function name. If you follow older tutorials you will see `stepCountIs`. AI SDK 7.0.0 (released June 25, 2026) [renamed `stepCountIs` to `isStepCount`](https://github.com/vercel/ai/blob/main/packages/ai/CHANGELOG.md) in its changelog. The old name was not deleted — both are still exported, and a quick identity check confirms they are literally the same function reference, so existing code keeps working. `isStepCount` is just the current spelling.

`stopWhen` takes more than a step count. `hasToolCall('someTool')` stops the loop the moment a specific tool fires, and you can pass an array of conditions that combine with OR semantics. But `isStepCount(n)` is the one you want by default, because it is your hard ceiling against a model that keeps calling tools forever.

## The `Agent` class loops for you

Writing `stopWhen` on every call gets old, which is why AI SDK 6 and 7 ship a higher-level abstraction: the `Agent` class (exported as `Experimental_Agent`, and aliased to `ToolLoopAgent` — again, the same constructor under two names). An `Agent` bundles a model, tools, and settings into a reusable object, and crucially it loops by default.

```ts
import { Experimental_Agent as Agent } from 'ai';

const agent = new Agent({ model, tools: { weather } });
const result = await agent.generate({ prompt: 'What is the weather in Paris?' });
// result.text === 'It is 21C and clear in Paris.'
```

No `stopWhen` in sight, yet this produces the full answer. That is because AI SDK 6.0.0 (released December 22, 2025) [set a default `stopWhen` on the Agent to `isStepCount(20)`](https://github.com/vercel/ai/blob/main/packages/ai/CHANGELOG.md). The Agent will run the tool loop for up to twenty steps on your behalf. If a misbehaving model never stops asking for tools, the Agent stops it at step twenty and returns with `finishReason: 'tool-calls'` — the same honest signal, now acting as a guardrail rather than a surprise.

This split is deliberate. `generateText` stays a sharp, predictable primitive that does exactly one thing per call, and the loop — the part that costs money and can run away — is an explicit choice you make by adding `stopWhen` or by reaching for the `Agent`.

## A testing trap worth knowing

To make the demo below deterministic I used `MockLanguageModelV4` instead of a real provider, and that surfaced a second thing older material gets wrong. AI SDK 7 speaks the v4 language-model spec, and the shape a mock must return has changed. `finishReason` is no longer a bare string — it is an object, `{ unified: 'tool-calls', raw: 'tool-calls' }`. Token usage is nested, with `inputTokens` and `outputTokens` each being objects rather than plain numbers. If you copy a `MockLanguageModelV2` snippet from a 2025 tutorial and hand back `finishReason: 'tool-calls'` as a string, the SDK reads `finishReason.unified` as `undefined`, decides the step was terminal, and your loop silently refuses to continue. I hit exactly that before checking the installed type definitions.

## Try It Yourself

Everything above is verifiable without an API key. A `MockLanguageModelV4` plays the model, so the output is identical on every run.

Setup:

```bash
mkdir aisdk-agent-loop && cd aisdk-agent-loop
npm init -y && npm pkg set type=module
npm install ai@7.0.71 zod@4.4.3
```

The script defines a weather tool, then runs the same prompt four ways. Counters track how many times the model was invoked and how many times the tool actually executed:

```js
import { generateText, Experimental_Agent as Agent, isStepCount, tool } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { z } from 'zod';

const usage = { inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 5, text: 5, reasoning: 0 }, totalTokens: 15 };
const finish = (r) => ({ unified: r, raw: r });

function scenario() {
  let modelCalls = 0, toolRuns = 0;
  const weather = tool({ description: 'Get the current weather for a city',
    inputSchema: z.object({ city: z.string() }),
    execute: async ({ city }) => { toolRuns++; return { city, tempC: 21, sky: 'clear' }; } });
  const model = new MockLanguageModelV4({ doGenerate: async () => {
    modelCalls++;
    if (modelCalls === 1) return { finishReason: finish('tool-calls'), usage, warnings: [],
      content: [{ type: 'tool-call', toolCallId: 'c1', toolName: 'weather',
        input: JSON.stringify({ city: 'Paris' }) }] };
    return { finishReason: finish('stop'), usage, warnings: [],
      content: [{ type: 'text', text: 'It is 21C and clear in Paris.' }] };
  } });
  return { model, weather, calls: () => modelCalls, runs: () => toolRuns };
}
```

Scenario 1 is the plain call with no `stopWhen`; scenario 2 adds `stopWhen: isStepCount(5)`; scenario 3 uses the `Agent` with no `stopWhen`; scenario 4 points an `Agent` at a model that never stops asking for tools, to find the default cap. Running all four prints:

```text
[1] generateText, no stopWhen
    steps=1 modelCalls=1 toolRuns=1 finishReason=tool-calls
    final text: ""

[2] generateText, stopWhen: isStepCount(5)
    steps=2 modelCalls=2 toolRuns=1 finishReason=stop
    final text: "It is 21C and clear in Paris."

[3] new Agent({...}).generate(), no stopWhen
    steps=2 modelCalls=2 finishReason=stop
    final text: "It is 21C and clear in Paris."

[4] Agent + a model that never stops calling tools
    steps=20 modelCalls=20 finishReason=tool-calls

[exports] stepCountIs === isStepCount: true
[exports] Experimental_Agent === ToolLoopAgent: true
```

Read the counters. In scenario 1 the tool ran once (`toolRuns=1`) but the model was called only once, so no text came back. In scenario 2 the model was called twice and produced the answer. Scenario 3 shows the `Agent` reaching the same two-step result with zero configuration. Scenario 4 pins the default ceiling at exactly 20 steps. The full runnable file is in the walkthrough repo linked below.

## Key Takeaways

- `generateText` and `streamText` in AI SDK 7 run a **single step** by default. If that step is a tool call, the tool executes but the model never sees the result, and `text` comes back empty with `finishReason: 'tool-calls'`.
- Add `stopWhen` to enable the loop. `isStepCount(n)` is the current name (AI SDK 7 renamed `stepCountIs`; both still work and are the same function). It is your hard ceiling on runaway tool loops.
- The `Agent` class (`Experimental_Agent` / `ToolLoopAgent`) loops for you, defaulting to `isStepCount(20)` since AI SDK 6.
- When mocking for tests under AI SDK 7's v4 spec, `finishReason` is an object (`{ unified, raw }`) and usage is nested. Old `MockLanguageModelV2` string shapes will silently break the loop.
- An empty answer after a tool call is almost never a model problem. It is a missing `stopWhen`.

**Sources:** [`ai` on npm](https://www.npmjs.com/package/ai) (7.0.71, published 2026-08-20; 7.0.0 2026-06-25; 6.0.0 2025-12-22; 5.0.0 2025-07-31), the [`ai` package CHANGELOG](https://github.com/vercel/ai/blob/main/packages/ai/CHANGELOG.md) (entries "rename `stepCountIs` to `isStepCount`" under 7.0.0 and "set default stopWhen on Agent to isStepCount(20)" under 6.0.0), and direct inspection plus execution of the installed `ai@7.0.71` and `@ai-sdk/provider` packages, including the `LanguageModelV4GenerateResult` type and the runnable script above.
