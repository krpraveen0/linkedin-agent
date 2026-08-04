"""
XGrammar demo 1: what "constrained decoding" actually constrains.

We build a tiny, explicit vocabulary so every token has a readable name,
compile a JSON schema into a grammar, and print exactly which tokens the
grammar allows at each step. No model, no GPU, no network.

    pip install xgrammar
    python demo1_bitmask.py
"""
import xgrammar as xgr
from xgrammar.testing import bitmask_to_bool_mask

# A tiny, explicit vocabulary. Each entry is one token the "model" can emit.
vocab = [
    "{", "}", "[", "]", ":", ",", '"',      # 0-6  JSON structural tokens
    "name", "age", "city",                    # 7-9  key text
    "Ada", "42", "true", "false", "null",     # 10-14 value text
    " ", "hello", "<eos>",                     # 15-17 misc + stop
]
STOP = vocab.index("<eos>")

info = xgr.TokenizerInfo(vocab, vocab_type=xgr.VocabType.RAW, stop_token_ids=[STOP])
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
    tid = vocab.index(tokstr)
    ok = matcher.accept_token(tid)
    print(f"accept {tokstr!r} -> {ok}; next allowed:", allowed(matcher))
