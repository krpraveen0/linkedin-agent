// AI SDK 7: the tool-calling loop is opt-in for the low-level primitives.
// Deterministic demo — no API key, no network. A MockLanguageModelV4 plays
// the model so every run prints identical, real output.
import {
  generateText,
  Experimental_Agent as Agent,
  ToolLoopAgent,
  isStepCount,
  stepCountIs,
  tool,
} from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { z } from 'zod';

// The v4 provider spec: finishReason is an object, usage is nested.
const usage = {
  inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 5, text: 5, reasoning: 0 },
  totalTokens: 15,
};
const finish = (r) => ({ unified: r, raw: r });

// A fresh model + tool per scenario, so we can count calls and executions.
function scenario() {
  let modelCalls = 0;
  let toolRuns = 0;
  const weather = tool({
    description: 'Get the current weather for a city',
    inputSchema: z.object({ city: z.string() }),
    execute: async ({ city }) => {
      toolRuns++;
      return { city, tempC: 21, sky: 'clear' };
    },
  });
  const model = new MockLanguageModelV4({
    doGenerate: async () => {
      modelCalls++;
      if (modelCalls === 1) {
        // Turn 1: the model asks for the tool.
        return {
          finishReason: finish('tool-calls'),
          usage,
          content: [
            { type: 'tool-call', toolCallId: 'c1', toolName: 'weather',
              input: JSON.stringify({ city: 'Paris' }) },
          ],
          warnings: [],
        };
      }
      // Turn 2+: the model writes the answer.
      return {
        finishReason: finish('stop'),
        usage,
        content: [{ type: 'text', text: 'It is 21C and clear in Paris.' }],
        warnings: [],
      };
    },
  });
  return { model, weather, calls: () => modelCalls, runs: () => toolRuns };
}

const prompt = 'What is the weather in Paris?';

// 1. Raw generateText, no stopWhen: one step, then it stops.
const a = scenario();
const r1 = await generateText({ model: a.model, tools: { weather: a.weather }, prompt });
console.log('[1] generateText, no stopWhen');
console.log('    steps=%d modelCalls=%d toolRuns=%d finishReason=%s',
  r1.steps.length, a.calls(), a.runs(), r1.finishReason);
console.log('    final text: %j', r1.text);

// 2. Same call + stopWhen: the SDK feeds the tool result back and loops.
const b = scenario();
const r2 = await generateText({
  model: b.model, tools: { weather: b.weather }, prompt,
  stopWhen: isStepCount(5),
});
console.log('\n[2] generateText, stopWhen: isStepCount(5)');
console.log('    steps=%d modelCalls=%d toolRuns=%d finishReason=%s',
  r2.steps.length, b.calls(), b.runs(), r2.finishReason);
console.log('    final text: %j', r2.text);

// 3. The Agent class loops by default (no stopWhen needed).
const c = scenario();
const agent = new Agent({ model: c.model, tools: { weather: c.weather } });
const r3 = await agent.generate({ prompt });
console.log('\n[3] new Agent({...}).generate(), no stopWhen');
console.log('    steps=%d modelCalls=%d finishReason=%s', r3.steps.length, c.calls(), r3.finishReason);
console.log('    final text: %j', r3.text);

// 4. The Agent default cap is isStepCount(20): a runaway model is bounded.
const d = (() => {
  let calls = 0;
  const spin = tool({ description: 'noop', inputSchema: z.object({}), execute: async () => ({ ok: true }) });
  const model = new MockLanguageModelV4({
    doGenerate: async () => {
      calls++;
      return { finishReason: finish('tool-calls'), usage,
        content: [{ type: 'tool-call', toolCallId: 'c' + calls, toolName: 'spin', input: '{}' }], warnings: [] };
    },
  });
  return { model, spin, calls: () => calls };
})();
const runaway = new Agent({ model: d.model, tools: { spin: d.spin } });
const r4 = await runaway.generate({ prompt: 'loop forever' });
console.log('\n[4] Agent + a model that never stops calling tools');
console.log('    steps=%d modelCalls=%d finishReason=%s', r4.steps.length, d.calls(), r4.finishReason);

// What the exports actually are in v7 (contradicting a few tutorials).
console.log('\n[exports] stepCountIs === isStepCount:', stepCountIs === isStepCount);
console.log('[exports] Experimental_Agent === ToolLoopAgent:', Agent === ToolLoopAgent);
