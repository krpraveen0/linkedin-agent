"""
XGrammar demo 3: how much does the mask cost per token?

We scale up to a 128,000-token vocabulary (roughly Llama-3 size) and time the
two hot-path calls separately: computing which tokens are legal
(fill_next_token_bitmask) versus applying that mask to the logits
(apply_token_bitmask_inplace) on CPU.

Timing numbers vary by machine and run; the point is the *ratio*.

    pip install xgrammar
    python demo3_timing.py
"""
import time
import xgrammar as xgr
import torch

# ~128K-token vocab: JSON structural tokens + filler text tokens.
base = ["{", "}", "[", "]", ":", ",", '"', " ", "name", "age", "true", "false", "null", "<eos>"]
vocab = base + [f"tok{i}" for i in range(128000 - len(base))]
info = xgr.TokenizerInfo(vocab, vocab_type=xgr.VocabType.RAW, stop_token_ids=[13])
print("vocab_size =", info.vocab_size)

t0 = time.perf_counter()
compiled = xgr.GrammarCompiler(info).compile_json_schema(
    '{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}')
print("one-time grammar compile: %.2f ms" % ((time.perf_counter() - t0) * 1e3))

matcher = xgr.GrammarMatcher(compiled)
mask = xgr.allocate_token_bitmask(1, info.vocab_size)
logits = torch.zeros(1, info.vocab_size)

N = 1000
matcher.fill_next_token_bitmask(mask, 0)  # warm up
t0 = time.perf_counter()
for _ in range(N):
    matcher.fill_next_token_bitmask(mask, 0)
fill_us = (time.perf_counter() - t0) / N * 1e6

t0 = time.perf_counter()
for _ in range(N):
    xgr.apply_token_bitmask_inplace(logits, mask)
apply_us = (time.perf_counter() - t0) / N * 1e6
print("fill_next_token_bitmask: %.1f us/token" % fill_us)
print("apply_token_bitmask_inplace (CPU): %.1f us/token" % apply_us)
