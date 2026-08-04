# XGrammar token bitmask: constrained decoding, concretely

Code for the 2026-08-04 Medium article *"Constrained Decoding, Concretely: XGrammar Ruled Out 127,999 of 128,000 Tokens Before My Model Said a Word."*

These three scripts show what grammar-constrained decoding actually does to an LLM's
next-token distribution. They run on **CPU only** — no model weights, no GPU, no network.
Instead of downloading a real tokenizer, they define a small explicit vocabulary so every
token has a readable name.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # optional
pip install xgrammar
```

Verified against `xgrammar==0.2.4` (Python 3.11). Installing `xgrammar` pulls in `torch`
and `transformers` as dependencies; only `torch` is used here (CPU).

## Run

### 1. Which tokens does the grammar allow at each step?

```bash
python demo1_bitmask.py
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

At step 0 only `{` is legal. After the opening quote, the only legal token is `name` —
the schema's required key is *forced*, not merely validated afterward.

### 2. The bitmask overriding a confident-but-wrong model

```bash
python demo2_logits.py
```

Real captured output:

```
argmax BEFORE mask: hello (logit 6.0 )
argmax AFTER  mask: { (logit 0.10000000149011612 )
row after mask: [0.1, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf, -inf]
accept 'hello' (id 16) at start: False
```

The model wanted `hello` (logit 6.0). After `apply_token_bitmask_inplace`, every illegal
token is `-inf`, so the argmax is `{`. An out-of-grammar token is hard-rejected by
`accept_token` (`False`).

### 3. Cost per token at a realistic (128K) vocabulary

```bash
python demo3_timing.py
```

Real captured output (timings vary by machine and run):

```
vocab_size = 128000
one-time grammar compile: 145.93 ms
fill_next_token_bitmask: 3.0 us/token
apply_token_bitmask_inplace (CPU): 673.3 us/token
```

Computing the mask is a few microseconds per token (a fresh independent rerun measured
2.4–2.5 µs). Applying it to a 128K-wide logit row on CPU is far more expensive — that step
runs fused on the GPU in real serving (`cuda`/`triton`/`torch.compile` backends).

## Sources

- [XGrammar GitHub repository](https://github.com/mlc-ai/xgrammar)
- [XGrammar paper — arXiv 2411.15100 (Nov 22 2024)](https://arxiv.org/abs/2411.15100)
- [MLC blog (Nov 22 2024)](https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar)
- [XGrammar-2 — arXiv 2601.04426 (Jan 2026; ACM CAIS '26)](https://arxiv.org/abs/2601.04426)
