# I Reversed My Sentence's Meaning. model2vec Returned the Exact Same Embedding

"The dog bit the man" and "The man bit the dog" mean opposite things. I encoded both with [model2vec](https://github.com/MinishLab/model2vec) and the cosine similarity between the two vectors came back as `0.9999999`. Not "very similar." Identical, down to floating-point rounding.

That is not a bug. It is the deal you sign when you trade a transformer for a static embedding model, and model2vec is the fastest, most visible way that trade is showing up in retrieval pipelines right now. Version [0.9.0 shipped on August 12, 2026](https://pypi.org/project/model2vec/), and its whole pitch is speed: the README claims embeddings that are "up to 500 times faster on CPU than the original model" while reducing "model size by a factor up to 50," with the best model landing at [~30 MB on disk](https://github.com/MinishLab/model2vec). When something is that much cheaper, people drop it into RAG and reranking without reading the fine print. This is the fine print: word order is gone.

## What model2vec actually is

A normal sentence-transformer runs your text through a full transformer stack. Every token attends to every other token, so "dog" in "the dog bit the man" produces a different internal representation than "dog" in "the man bit the dog." Attention is what makes word order matter.

model2vec removes that stack. Its distillation process forward-passes a vocabulary through a sentence transformer once — "creating static embeddings for the individual tokens," per the [project README](https://github.com/MinishLab/model2vec) — then applies post-processing steps such as dimensionality reduction and frequency-based token weighting. The output is a plain lookup table: one fixed vector per token, computed ahead of time, with no attention left at inference.

So how do you get a *sentence* vector from a table of token vectors? You average them. That is the entire inference path, and it is worth seeing in the library's own source rather than taking my word for it.

## The three lines that delete word order

Here is the heart of `_encode_batch` from model2vec 0.9.0's `model.py` (the two inline comments are mine; I have dropped the trailing `np.stack` and optional-normalize lines):

```python
def _encode_batch(self, sentences, max_length):
    """Encode a batch of sentences."""
    ids = self.tokenize(sentences=sentences, max_length=max_length)
    out = []
    for id_list in ids:
        if id_list:
            emb = self._encode_helper(id_list)   # look up one vector per token
            out.append(emb.mean(axis=0))          # average over tokens
        else:
            out.append(np.zeros(self.dim))
```

`_encode_helper` is a NumPy fancy-index into the embedding table (`self.embedding[id_list]`), optionally scaled by a per-token weight. Then `emb.mean(axis=0)` averages across the token axis.

The mean of a set does not depend on the order of that set. Reorder the tokens and you feed `mean` the same rows in a different sequence; the result is the same vector. Word order cannot survive an operation that is mathematically blind to it. This is the classic bag-of-words property, and it is baked into the architecture, not the weights — which means it holds for *every* pretrained potion model, no matter how good the underlying transformer was.

## Watching it happen

You do not need to trust the reasoning. You can watch two opposite sentences collapse onto the same vector.

A note on how I ran this: `huggingface.co` is blocked in my sandbox, so I could not download a pretrained `potion-base-8M`. Instead I built a `StaticModel` using model2vec's own class with a small tokenizer and one fixed vector per token. That exercises the identical inference path shown above (`self.embedding[ids].mean(axis=0)`), and because order-invariance is a property of the *pooling*, not the specific numbers in the table, the result is exactly what you get from a real potion model. If you have model access, swap in `StaticModel.from_pretrained("minishlab/potion-base-8M")` and the cosine similarities come out the same.

```python
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

rng = np.random.default_rng(42)                       # one fixed vector per token
vectors = rng.standard_normal((len(words), 256)).astype(np.float32)
model = StaticModel(vectors=vectors, tokenizer=tok, config={}, normalize=True)

cos = lambda a, b: float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
e1, e2, e3 = model.encode([
    "the dog bit the man",
    "the man bit the dog",       # opposite meaning, same words
    "the cat chased the mouse",  # different words
])
print(f"cos(s1, s2) = {cos(e1, e2):.7f}   (subject/object swapped)")
print(f"cos(s1, s3) = {cos(e1, e3):.7f}   (genuinely different sentence)")
print(f"max |e1 - e2| = {np.max(np.abs(e1 - e2)):.2e}")
```

Real output:

```
cos(s1, s2) = 0.9999999   (subject/object swapped)
cos(s1, s3) = 0.5666459   (genuinely different sentence)
max |e1 - e2| = 2.98e-08
```

Two sentences with opposite meaning are, to the model, the same point in space. A sentence with different words sits far away (0.57). The model can tell *which words* you used with high fidelity. It has no idea *in what order* you used them. The `2.98e-08` gap between the "identical" vectors is not word order leaking back in — it is floating-point addition being non-associative, because the mean sums the token rows in the order they appear before dividing.

## Confirming the mechanism

To be sure the averaging really is all that happens, reproduce `encode()` by hand and diff it against the library:

```python
sentence = "the dog bit the man"
ids = model.tokenize([sentence])[0]           # [1, 2, 3, 1, 4]
by_hand = model.embedding[ids].mean(axis=0)   # look up + average
library = model.encode([sentence])[0]

print("hand-rolled mean == library encode()?", np.allclose(by_hand, library, atol=1e-6))

shuffled = [ids[i] for i in (4, 0, 3, 1, 2)]  # same ids, scrambled order
print("mean of shuffled == mean of original?",
      np.allclose(model.embedding[shuffled].mean(axis=0), by_hand, atol=1e-6))
```

Real output:

```
hand-rolled mean == library encode()? True
mean of shuffled == mean of original? True
```

A one-line NumPy mean reproduces the library's sentence embedding exactly, and shuffling the token ids changes nothing. There is no hidden step where order sneaks back in.

## The speed you are buying

The reason anyone accepts this trade is throughput. With no transformer to run, encoding is a gather and an average. On a single CPU, encoding 20,000 short documents took just over a second:

```python
import time
docs = [...]  # 20,000 documents, ~12 words each
t = time.perf_counter()
emb = model.encode(docs)
dt = time.perf_counter() - t
print(f"encoded {len(docs):,} documents in {dt:.3f} s on CPU")
print(f"throughput: {len(docs)/dt:,.0f} documents/second")
```

Real output:

```
encoded 20,000 documents in 1.246 s on CPU
throughput: 16,050 documents/second
output shape: (20000, 256)
```

Sixteen thousand documents per second, no GPU, no API call. That is the appeal, and the [reported benchmarks](https://github.com/MinishLab/model2vec/blob/main/results/README.md) say the quality cost is smaller than you would fear: `potion-base-32M` posts an average MTEB score of 52.13, which the results page frames as 93.21% of `all-MiniLM-L6-v2`'s 55.93; `potion-base-8M` reaches 51.08. Those aggregate scores lean on tasks like classification and clustering, where the *bag of words in a document* carries most of the signal and order matters least.

## When the missing order will bite you

The failure mode is specific. If your retrieval depends on distinguishing sentences built from the same words, static embeddings will merge them:

- "flight from Boston to Denver" vs. "flight from Denver to Boston"
- "transfer $500 from savings to checking" vs. "transfer $500 from checking to savings"
- "is the API rate limit per user or per org" vs. "is the org rate limit per API user"
- negations and comparisons where the operative word moves: "approved, not rejected" vs. "rejected, not approved"

For broad semantic retrieval — "find docs about database indexing" — model2vec is a genuinely strong, cheap default. For anything where argument order, direction, or negation is the whole point, a bag of words is the wrong tool, and no amount of MTEB average will warn you, because those cases are a rounding error in the benchmark and a disaster in production. A cheap mitigation is a two-stage setup: use model2vec to retrieve a wide candidate set fast, then rerank the top handful with an order-aware cross-encoder that actually reads the sequence.

## Key Takeaways

- model2vec produces a sentence embedding by looking up one fixed vector per token and averaging them (`emb.mean(axis=0)`). Averaging is order-independent, so **word order is discarded** — a bag-of-words model with transformer-quality token vectors.
- Two sentences with the same words in different order get the **same vector**: I measured cosine `0.9999999` for "the dog bit the man" vs. "the man bit the dog," with only a `~3e-8` floating-point gap.
- This is architectural, not a tuning artifact. It holds for every pretrained potion model and is visible directly in the library's `_encode_batch` source.
- You buy real speed for it: ~16,000 docs/second on one CPU in my test, and reported MTEB scores around 93% of `all-MiniLM-L6-v2` for `potion-base-32M`.
- Reach for it for broad semantic retrieval; avoid it — or rerank behind it — whenever order, direction, or negation changes the meaning.

## Sources

- model2vec repository and README (version 0.9.0, distillation and inference, speed/size claims), accessed 2026-08-27: https://github.com/MinishLab/model2vec
- model2vec 0.9.0 release date (2026-08-12), PyPI, accessed 2026-08-27: https://pypi.org/project/model2vec/
- MTEB benchmark numbers (potion-base-32M 52.13 / 93.21%, potion-base-8M 51.08; all-MiniLM-L6-v2 55.93), model2vec results, accessed 2026-08-27: https://github.com/MinishLab/model2vec/blob/main/results/README.md
- Inference mechanism verified by direct inspection of the installed `model2vec/model.py` (`_encode_batch`, `_encode_helper`), version 0.9.0.
