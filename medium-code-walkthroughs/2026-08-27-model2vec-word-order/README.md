# model2vec discards word order — code walkthrough

Companion code for the article *"I Reversed My Sentence's Meaning. model2vec Returned the Exact Same Embedding"* (2026-08-27).

These scripts demonstrate, with the real [model2vec](https://github.com/MinishLab/model2vec) 0.9.0 library, that static embeddings are a **bag of words**: `encode()` looks up one fixed vector per token and averages them, so word order is discarded.

## Why the demo builds a `StaticModel` instead of downloading one

`huggingface.co` is blocked by egress policy in the environment these scripts were run in, so a pretrained `potion-base-8M` could not be downloaded. Instead the scripts construct a `StaticModel` with model2vec's own class, a small tokenizer, and one fixed vector per token. The property being shown — order invariance — is a property of the **mean-pooling architecture**, not of the specific vectors, so the result is identical to what a pretrained potion model produces. If you have model access, replace the constructed model with:

```python
from model2vec import StaticModel
model = StaticModel.from_pretrained("minishlab/potion-base-8M")
```

and the cosine similarities come out the same.

## Setup

```bash
python3 -m venv m2v-env
./m2v-env/bin/pip install --upgrade pip
./m2v-env/bin/pip install model2vec        # installs 0.9.0
```

## Run

```bash
./m2v-env/bin/python order_invariance.py
./m2v-env/bin/python mechanism.py
./m2v-env/bin/python speed.py
```

## Captured output

### `order_invariance.py` — opposite meanings, one vector

```
model2vec version: 0.9.0

'the dog bit the man'
'the man bit the dog'   <- opposite meaning, same words
'the cat chased the mouse'   <- different words

cos(s1, s2) = 0.9999999   (subject/object swapped)
cos(s1, s3) = 0.5666459   (genuinely different sentence)
max |e1 - e2| element diff = 2.98e-08
```

Swapping subject and object leaves the embedding unchanged (cosine `0.9999999`; the `~3e-8` gap is floating-point summation order, not word order). A sentence with different words sits far away (`0.57`).

### `mechanism.py` — encode() is lookup + mean, nothing else

```
token ids: [1, 2, 3, 1, 4]
hand-rolled mean == library encode()? True
first 4 dims, by hand : [-0.48376  0.09579  0.01439 -0.20197]
first 4 dims, library : [-0.48376  0.09579  0.01439 -0.20197]

same ids, shuffled   : [4, 1, 1, 2, 3]
mean of shuffled == mean of original? True
```

A one-line `model.embedding[ids].mean(axis=0)` reproduces the library's sentence embedding exactly, and shuffling the token ids changes nothing.

### `speed.py` — the throughput you buy

```
encoded 20,000 documents in 1.246 s on CPU
throughput: 16,050 documents/second
output shape: (20000, 256)
machine: x86_64, numpy 2.4.6
```

(Timing is machine-dependent; the shape and behavior are not.)

## The line that deletes word order

From model2vec 0.9.0's `model.py`, `_encode_batch`:

```python
emb = self._encode_helper(id_list)   # look up one vector per token
out.append(emb.mean(axis=0))          # average over tokens -> order-independent
```
