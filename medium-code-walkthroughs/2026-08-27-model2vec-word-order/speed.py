"""Measure model2vec's raw CPU throughput. No GPU, no network."""
import time
import numpy as np
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from model2vec import StaticModel

words = ["[UNK]"] + [f"w{i}" for i in range(30000)]
tok = Tokenizer(WordLevel(vocab={w: i for i, w in enumerate(words)}, unk_token="[UNK]"))
tok.pre_tokenizer = Whitespace()
rng = np.random.default_rng(0)
vectors = rng.standard_normal((len(words), 256)).astype(np.float32)
model = StaticModel(vectors=vectors, tokenizer=tok, config={}, normalize=True)

# 20k short docs, ~12 words each
docs = [" ".join(f"w{int(rng.integers(0, 30000))}" for _ in range(12)) for _ in range(20000)]
model.encode(docs[:100])  # warm up

t = time.perf_counter()
emb = model.encode(docs)
dt = time.perf_counter() - t
print(f"encoded {len(docs):,} documents in {dt:.3f} s on CPU")
print(f"throughput: {len(docs)/dt:,.0f} documents/second")
print(f"output shape: {emb.shape}")
import platform
print(f"machine: {platform.processor() or platform.machine()}, numpy {np.__version__}")
