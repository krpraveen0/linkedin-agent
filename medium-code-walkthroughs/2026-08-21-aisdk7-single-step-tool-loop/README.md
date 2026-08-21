# Why an AI SDK tool call can return an empty answer

Runnable code for the article **"I Asked My AI SDK Agent for the Weather. It Fetched It, Then Handed Back an Empty String."**

It shows that in the [Vercel AI SDK](https://www.npmjs.com/package/ai) 7, `generateText` runs a **single step** by default: when the model calls a tool, the tool executes but the model never sees the result, so you get `finishReason: 'tool-calls'` and empty `text`. Adding `stopWhen: isStepCount(n)` — or using the `Agent` class, which loops by default — turns it into a real agent loop.

No API key and no network: a `MockLanguageModelV4` plays the model, so the output is byte-identical on every run.

Verified against `ai@7.0.71` (published 2026-08-20) and `zod@4.4.3` on Node v22.

## Files

- `agent-loop.mjs` — defines a weather tool and runs the same prompt four ways: plain `generateText`, `generateText` with `stopWhen`, an `Agent` (loops by default), and an `Agent` pointed at a model that never stops calling tools (to find the default 20-step cap).
- `figure1-single-vs-loop.svg`, `figure2-steploop.svg` — the two diagrams from the article.
- `article.md` — the article itself.

## Setup

Requires Node 18+ (Node 22 used here).

```bash
npm init -y && npm pkg set type=module
npm install ai@7.0.71 zod@4.4.3
```

## Run

```bash
node agent-loop.mjs
```

## Real captured output

```
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

## What to read in the output

- **Scenario 1**: the tool ran (`toolRuns=1`) but the model was called only once, so no answer came back — `text` is empty and `finishReason` is `tool-calls`.
- **Scenario 2**: `stopWhen: isStepCount(5)` feeds the tool result back; the model is called a second time and writes the answer (`finishReason: stop`).
- **Scenario 3**: the `Agent` class reaches the same two-step answer with no `stopWhen` — it defaults to `isStepCount(20)` (AI SDK 6+).
- **Scenario 4**: a runaway model is bounded at exactly 20 steps.
- **Exports**: `stepCountIs` and `isStepCount` are the same function (AI SDK 7 renamed it, kept the alias); `Experimental_Agent` and `ToolLoopAgent` are the same constructor.

## Note on mocking

Under AI SDK 7's v4 language-model spec, a mock's `doGenerate` must return `finishReason` as an object (`{ unified, raw }`) and nested `usage` (`inputTokens`/`outputTokens` as objects). Older `MockLanguageModelV2` snippets that return `finishReason: 'tool-calls'` as a string cause the SDK to read `finishReason.unified` as `undefined` and silently stop the loop.
