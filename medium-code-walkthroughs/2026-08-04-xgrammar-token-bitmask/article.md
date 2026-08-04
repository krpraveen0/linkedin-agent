# Constrained Decoding, Concretely: XGrammar Ruled Out 127,999 of 128,000 Tokens Before My Model Said a Word

Ask an LLM for JSON and it usually gives you JSON. Usually. The failure cases are the ones that page you at 2 a.m.: a stray markdown fence, a trailing comma, a hallucinated field, a string that never closes. Retrying with "please return valid JSON" is a probabilistic patch on a probabilistic problem.

Constrained decoding takes a different route. Instead of hoping the model stays inside a schema, it makes every illegal token literally impossible to sample. The engine that does this in most production inference stacks today is [XGrammar](https://github.com/mlc-ai/xgrammar), and its own README states plainly that it is "the default structured generation backend for most LLM inference engines, including vLLM, SGLang, TensorRT-LLM, and MLC-LLM."

I wanted to see the constraint happen rather than read about it. So I built a toy tokenizer, compiled a JSON schema into a grammar, and printed exactly which tokens XGrammar allowed at each step. At the very first step, with a 128,000-token vocabulary, it allowed exactly one.

## Why this is worth revisiting now

XGrammar is not new. The original paper ([arXiv 2411.15100](https://arxiv.org/abs/2411.15100), submitted November 22, 2024) introduced the adaptive token mask cache that made grammar-constrained decoding cheap enough to leave on by default. What changed recently is the direction of travel toward *agentic* workloads.

In January 2026 the same group published [XGrammar-2](https://arxiv.org/abs/2601.04426) ("Efficient Dynamic Structured Generation Engine for Agentic LLMs"), presented at the ACM Conference on AI and Agentic Systems in May 2026. The motivation is specific: agents don't emit one static schema per request. They switch structure mid-stream, plain text, then a tool call, then a response envelope, then more text. XGrammar-2 reports over 6x faster grammar compilation and adds machinery (TagDispatch, a Cross-Grammar Cache) aimed at exactly that dynamic switching. If your agent does tool calling, the code path that keeps its output well-formed is now a first-class performance concern, not a formatting afterthought.

Which makes it a good moment to understand what the constraint mechanism actually does to your model's next-token distribution.

## The whole idea is a bitmask over the vocabulary

At each decoding step, an LLM produces one logit per vocabulary token. Sampling picks from that distribution. Grammar-constrained decoding inserts one operation between the logits and the sampler: a **token bitmask**, one bit per token, `1` for "legal here" and `0` for "illegal here." XGrammar sets the logits of every illegal token to negative infinity, so the sampler cannot pick them no matter how confident the model was.

The reason this is fast rather than ruinous is the paper's central observation: for any given grammar, the overwhelming majority of vocabulary tokens are *context-independent*. Their legality doesn't depend on what's been generated so far, so it can be precomputed once when the grammar is compiled. The XGrammar paper and the [MLC blog post](https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar) (November 22, 2024) put the context-independent share at over 99% of tokens, which is why the per-token mask generation on JSON grammars comes in under 40 microseconds, roughly 100x faster than earlier libraries.

Let me show the mask directly.

## Try it yourself

Everything below runs on CPU with no model and no network. Install the package (I used `xgrammar==0.2.4`):

```bash
pip install xgrammar
```

Rather than download a real tokenizer, I define an 18-token vocabulary by hand so every token has a readable name. Then I compile a one-field JSON schema and print the allowed set at each step.

```python
import xgrammar as xgr
from xgrammar.testing import bitmask_to_bool_mask

vocab = [
    "{", "}", "[", "]", ":", ",", '"',      # 0-6  JSON structural tokens
    "name", "age", "city",                    # 7-9  key text
    "Ada", "42", "true", "false", "null",     # 10-14 value text
    " ", "hello", "<eos>",                     # 15-17 misc + stop
]
info = xgr.TokenizerInfo(vocab, vocab_type=xgr.VocabType.RAW, stop_token_ids=[17])
schema = '{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}'
compiled = xgr.GrammarCompiler(info).compile_json_schema(schema)
matcher = xgr.GrammarMatcher(compiled)

def allowed(m):
    mask = xgr.allocate_token_bitmask(1, info.vocab_size)
    m.fill_next_token_bitmask(mask, 0)
    bools = bitmask_to_bool_mask(mask, info.vocab_size)[0]
    return [vocab[i] for i in range(info.vocab_size) if bool(bools[i])]

print("step 0 allowed:", allowed(matcher))
for tokstr in ["{", '"', "name", '"', ":"]:
    print(f"accept {tokstr!r} -> {matcher.accept_token(vocab.index(tokstr))};"
          f" next allowed:", allowed(matcher))
```

Real captured output:

```
step 0 allowed: ['{']
accept '{' -> True; next allowed: ['"', ' ']
accept '"' -> True; next allowed: ['name']
accept 'name' -> True; next allowed: ['"']
accept '"' -> True; next allowed: [':', ' ']
accept ':' -> True; next allowed: ['"', ' ']
```

Read that trace top to bottom. At step 0 the grammar allows a single token, `{`, because a JSON object can only begin one way. After the opening brace it allows a quote or a space. Here's the part I find genuinely useful: after the opening quote, the only allowed token is `name`. The schema marked `name` as a required property, so the grammar forces the key. The model has no opportunity to invent `nmae` or `naem` or any other field. The typo class of bug is not made unlikely; it is made unreachable.

Now watch the mask override a confident-but-wrong model. I hand XGrammar a row of logits where the highest scorer is `hello`, then apply the grammar's bitmask in place.

```python
import torch
logits = torch.tensor([[0.1, 3.0, 0.2, 0.0, 0.0, 0.0, 0.5,
                        2.0, 0.0, 0.0, 4.0, 0.0, 5.0, 0.0, 0.0, 0.1, 6.0, 0.0]])
print("argmax BEFORE mask:", vocab[int(logits.argmax())], "(logit", float(logits.max()), ")")

mask = xgr.allocate_token_bitmask(1, info.vocab_size)
matcher.fill_next_token_bitmask(mask, 0)
xgr.apply_token_bitmask_inplace(logits, mask)   # disallowed -> -inf, in place
print("argmax AFTER  mask:", vocab[int(logits.argmax())], "(logit", float(logits.max()), ")")
print("row after mask:", [round(float(x), 1) for x in logits[0]])
print("accept 'hello' (id 16) at start:", matcher.accept_token(16))
```

Real captured output:

```
argmax BEFORE mask: hello (logit 6.0 )
argmax AFTER  mask: { (logit 0.10000000149011612 )
row after mask: [0.1, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf]
accept 'hello' (id 16) at start: False
```

Before masking, the model wants `hello` (logit 6.0). After masking, every token except `{` is `-inf`, so the argmax is `{` with its unremarkable logit of 0.1. The model's preference is completely overruled by the grammar. The last line is the belt-and-suspenders check: if you try to feed the matcher an out-of-grammar token, `accept_token` returns `False`. The state machine refuses to advance on an illegal move.

## What it costs per token

Sub-40-microsecond mask generation is the headline number, so I measured it. I scaled the vocabulary to 128,000 tokens (roughly Llama-3 size) and timed the two hot-path calls separately: computing the mask, and applying it to the logits.

```python
import time
base = ["{","}","[","]",":",",",'"'," ","name","age","true","false","null","<eos>"]
vocab = base + [f"tok{i}" for i in range(128000 - len(base))]
info = xgr.TokenizerInfo(vocab, vocab_type=xgr.VocabType.RAW, stop_token_ids=[13])

t0 = time.perf_counter()
compiled = xgr.GrammarCompiler(info).compile_json_schema(schema)
print("one-time grammar compile: %.2f ms" % ((time.perf_counter()-t0)*1e3))

matcher = xgr.GrammarMatcher(compiled)
mask = xgr.allocate_token_bitmask(1, info.vocab_size)
logits = torch.zeros(1, info.vocab_size)
N = 1000
matcher.fill_next_token_bitmask(mask, 0)  # warm up
t0 = time.perf_counter()
for _ in range(N): matcher.fill_next_token_bitmask(mask, 0)
print("fill_next_token_bitmask: %.1f us/token" % ((time.perf_counter()-t0)/N*1e6))
t0 = time.perf_counter()
for _ in range(N): xgr.apply_token_bitmask_inplace(logits, mask)
print("apply_token_bitmask_inplace (CPU): %.1f us/token" % ((time.perf_counter()-t0)/N*1e6))
```

Real captured output (timings vary by machine and run):

```
vocab_size = 128000
one-time grammar compile: 145.93 ms
fill_next_token_bitmask: 3.0 us/token
apply_token_bitmask_inplace (CPU): 673.3 us/token
```

Computing which tokens are legal took about 3 microseconds per token, comfortably inside the paper's sub-40-microsecond claim, and it stayed there across reruns (a fresh independent run measured 2.4 to 2.5 microseconds). That is the part XGrammar is proud of, and it holds up.

The number that deserves a caveat is the other one. *Applying* the mask to a 128,000-wide logit row on CPU took around 670 microseconds, over 200x the cost of computing it. That is not a knock on XGrammar. Writing `-inf` across a large tensor is a memory-bandwidth operation, and in real serving it runs fused on the GPU alongside the rest of the sampling step, where `apply_token_bitmask_inplace` supports `cuda`, `triton`, and `torch.compile` backends. The lesson from the measurement is where the cost lives: the clever grammar work is nearly free, and the remaining expense is a bulk tensor write that belongs on the accelerator, not the CPU.

## Why the work happens before generation

The reason mask computation is a few microseconds and not a few milliseconds is that XGrammar front-loads it. Grammar compilation, the 146-millisecond step above, walks the schema once and precomputes the legality of every context-independent token, the 99%-plus that never change. At generation time the matcher only evaluates the small remainder that actually depends on position in the string. In a real serving stack that one-time compile also overlaps with prompt processing, so the user-visible latency of turning constraints on is close to zero.

XGrammar-2 pushes this further for agents. Its Cross-Grammar Cache reuses precomputed substructures *across different grammars*, so an agent that alternates between a tool-call schema and a response schema doesn't recompile shared pieces every time it switches. That is the whole point of the "over 6x faster compilation" figure: in agentic workloads you pay the compile cost far more often, so making it cheap is what keeps structured output from becoming the bottleneck.

## Key takeaways

- Grammar-constrained decoding is a token bitmask applied to logits: legal tokens pass, illegal tokens are set to `-inf`, and the sampler cannot pick them. I watched a 128,000-token vocabulary collapse to a single legal token at step 0.
- A `required` property in your JSON schema doesn't just get validated after the fact; XGrammar forces the exact key during generation, so misspelled or hallucinated field names are unreachable, not merely improbable.
- Mask *computation* is genuinely cheap (about 3 microseconds per token in my run, matching the paper's sub-40-microsecond claim). The larger cost is *applying* the mask to a wide logit row, which is a bulk tensor write meant for the GPU.
- The speed comes from front-loading: over 99% of tokens are context-independent and precomputed at compile time. XGrammar-2 (January 2026) extends that caching across grammars, which is what makes structured output cheap enough for tool-calling agents that switch structure mid-response.
- This is default infrastructure now. If you serve on vLLM, SGLang, TensorRT-LLM, or MLC-LLM, this bitmask is likely already deciding your model's next token whenever you pass a response schema.

*Sources: [XGrammar GitHub repository](https://github.com/mlc-ai/xgrammar); [XGrammar: Flexible and Efficient Structured Generation Engine for LLMs (arXiv 2411.15100, Nov 22 2024)](https://arxiv.org/abs/2411.15100); [MLC blog: Achieving Efficient, Flexible, and Portable Structured Generation with XGrammar (Nov 22 2024)](https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar); [XGrammar-2: Efficient Dynamic Structured Generation Engine for Agentic LLMs (arXiv 2601.04426, Jan 2026; ACM CAIS '26)](https://arxiv.org/abs/2601.04426). Code and real captured output verified against `xgrammar==0.2.4` on CPU.*
