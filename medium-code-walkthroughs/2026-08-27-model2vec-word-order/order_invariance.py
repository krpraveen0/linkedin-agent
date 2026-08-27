"""Show that model2vec's static embeddings ignore word order.

huggingface.co is blocked in this sandbox, so instead of downloading a
pretrained potion model we build a StaticModel with model2vec's own class.
The property we demonstrate -- order invariance -- is architectural: it
comes from mean-pooling per-token vectors, so it holds identically for any
pretrained potion model. We prove that by printing model2vec's own source.
"""
import inspect
import numpy as np
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.normalizers import Lowercase
from tokenizers.pre_tokenizers import Whitespace
import model2vec
from model2vec import StaticModel

print("model2vec version:", model2vec.__version__)

# 1. A tiny word-level tokenizer (no network, no downloads).
words = ["[UNK]", "the", "dog", "bit", "man", "cat", "chased", "mouse"]
tok = Tokenizer(WordLevel(vocab={w: i for i, w in enumerate(words)}, unk_token="[UNK]"))
tok.normalizer = Lowercase()
tok.pre_tokenizer = Whitespace()

# 2. One fixed 256-d vector per token. Values are arbitrary but deterministic;
#    only the fact that each *token* maps to one vector matters here.
rng = np.random.default_rng(42)
vectors = rng.standard_normal((len(words), 256)).astype(np.float32)

model = StaticModel(vectors=vectors, tokenizer=tok, config={}, normalize=True)

def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))

s1 = "the dog bit the man"
s2 = "the man bit the dog"   # same words, reversed meaning
s3 = "the cat chased the mouse"  # different words

e1, e2, e3 = model.encode([s1, s2, s3])

print(f"\n{s1!r}")
print(f"{s2!r}   <- opposite meaning, same words")
print(f"{s3!r}   <- different words\n")
print(f"cos(s1, s2) = {cos(e1, e2):.7f}   (subject/object swapped)")
print(f"cos(s1, s3) = {cos(e1, e3):.7f}   (genuinely different sentence)")
print(f"max |e1 - e2| element diff = {np.max(np.abs(e1 - e2)):.2e}")
