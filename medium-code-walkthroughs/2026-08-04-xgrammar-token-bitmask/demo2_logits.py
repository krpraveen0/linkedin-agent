"""
XGrammar demo 2: the bitmask meets real logits.

We hand XGrammar a fake row of logits where the model's favourite token is
"hello", apply the grammar's bitmask in place, and watch every illegal token
drop to -inf. We also show that an out-of-grammar token is hard-rejected by
the matcher, not merely down-weighted.

    pip install xgrammar
    python demo2_logits.py
"""
import xgrammar as xgr
import torch

vocab = ["{", "}", "[", "]", ":", ",", '"', "name", "age", "city",
         "Ada", "42", "true", "false", "null", " ", "hello", "<eos>"]
info = xgr.TokenizerInfo(vocab, vocab_type=xgr.VocabType.RAW, stop_token_ids=[17])
compiled = xgr.GrammarCompiler(info).compile_json_schema(
    '{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}')
matcher = xgr.GrammarMatcher(compiled)

# Pretend the model produced these raw logits (higher = more likely).
logits = torch.tensor([[0.1, 3.0, 0.2, 0.0, 0.0, 0.0, 0.5,
                        2.0, 0.0, 0.0, 4.0, 0.0, 5.0, 0.0, 0.0, 0.1, 6.0, 0.0]])
print("argmax BEFORE mask:", vocab[int(logits.argmax())], "(logit", float(logits.max()), ")")

mask = xgr.allocate_token_bitmask(1, info.vocab_size)
matcher.fill_next_token_bitmask(mask, 0)
xgr.apply_token_bitmask_inplace(logits, mask)   # disallowed -> -inf, in place
print("argmax AFTER  mask:", vocab[int(logits.argmax())], "(logit", float(logits.max()), ")")
print("row after mask:", [round(float(x), 1) for x in logits[0]])

# An out-of-grammar token is hard-rejected, not just down-weighted.
print("accept 'hello' (id 16) at start:", matcher.accept_token(16))
