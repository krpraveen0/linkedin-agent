"""
Chroma distance-metric footguns, demonstrated with fixed offline embeddings.

No model, no API: we pass our own vectors so every number is reproducible.
Query lives at [1, 0]. Doc A points the SAME direction (topically identical,
longer text -> larger magnitude). Doc B sits numerically NEAR the query but
points a different direction (short, off-topic chunk).

  cosine:      A is closest (same direction)
  squared L2:  B is closest (nearer coordinates)
"""
import chromadb

client = chromadb.Client()
QUERY = [1.0, 0.0]
DOCS = {"A_on_topic_long": [5.0, 0.0], "B_off_topic_short": [1.0, 1.0]}


def build(name, **kw):
    try:
        client.delete_collection(name)
    except Exception:
        pass
    col = client.create_collection(name, **kw)
    col.add(ids=list(DOCS), embeddings=list(DOCS.values()))
    return col


def top(col):
    r = col.query(query_embeddings=[QUERY], n_results=2)
    return list(zip(r["ids"][0], [round(d, 4) for d in r["distances"][0]]))


# 1. The default
d = build("default_store")
print("space         :", d.configuration_json["hnsw"]["space"])
print("ranking       :", top(d))

# 2. Cosine, set the modern way
c = build("cosine_store", configuration={"hnsw": {"space": "cosine"}})
print("\nspace         :", c.configuration_json["hnsw"]["space"])
print("ranking       :", top(c))

# 3. get_or_create on an existing collection: config is ignored, no warning
again = client.get_or_create_collection(
    "default_store", configuration={"hnsw": {"space": "cosine"}}
)
print("\nasked for     : cosine")
print("actually got  :", again.configuration_json["hnsw"]["space"])
print("ranking       :", top(again))

# 4. Can we fix it in place? modify() the space of the existing collection
try:
    d.modify(configuration={"hnsw": {"space": "cosine"}})
    print("\nmodify        : succeeded ->", d.configuration_json["hnsw"]["space"])
except Exception as e:
    print("\nmodify        :", type(e).__name__)
    print("               ", str(e).splitlines()[0][:96])
