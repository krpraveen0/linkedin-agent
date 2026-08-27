"""Prove *why* order vanishes: encode() is a token lookup + mean, nothing else."""
import numpy as np
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.normalizers import Lowercase
from tokenizers.pre_tokenizers import Whitespace
from model2vec import StaticModel

words = ["[UNK]", "the", "dog", "bit", "man", "cat", "chased", "mouse"]
tok = Tokenizer(WordLevel(vocab={w: i for i, w in enumerate(words)}, unk_token="[UNK]"))
tok.normalizer = Lowercase()
tok.pre_tokenizer = Whitespace()
rng = np.random.default_rng(42)
vectors = rng.standard_normal((len(words), 256)).astype(np.float32)
model = StaticModel(vectors=vectors, tokenizer=tok, config={}, normalize=False)

sentence = "the dog bit the man"

# What the library does internally:
ids = model.tokenize([sentence])[0]
print("token ids:", ids)

# Reproduce encode() by hand: look up each id, take the mean over tokens.
by_hand = model.embedding[ids].mean(axis=0)

# The library's own encode():
library = model.encode([sentence])[0]

print("hand-rolled mean == library encode()?",
      np.allclose(by_hand, library, atol=1e-6))
print("first 4 dims, by hand :", np.round(by_hand[:4], 5))
print("first 4 dims, library :", np.round(library[:4], 5))

# Order cannot matter: the mean of a set is independent of order.
shuffled_ids = [ids[i] for i in (4, 0, 3, 1, 2)]
print("\nsame ids, shuffled   :", shuffled_ids)
print("mean of shuffled == mean of original?",
      np.allclose(model.embedding[shuffled_ids].mean(axis=0), by_hand, atol=1e-6))
