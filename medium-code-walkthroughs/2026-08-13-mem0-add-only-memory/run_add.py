"""
Block 2 — Run mem0's REAL default add() pipeline end to end, fully offline.
Only the LLM and embedder are stubbed (so no API key / network is needed and the
run is deterministic). Everything else — retrieval, dedup, the decision of what
to do with an existing, contradicting memory, storage — is mem0's own code.

We tell the agent one thing, then tell it the opposite, and look at the store.
"""
import os, tempfile, logging
os.environ["MEM0_TELEMETRY"] = "False"
os.environ.setdefault("OPENAI_API_KEY", "sk-not-used-stub")
logging.getLogger("mem0").setLevel(logging.ERROR)  # hide optional-extra notices

from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.vector_stores.configs import VectorStoreConfig

DIM = 8

# --- Stub LLM: returns exactly the facts a real extractor would pull out. ---
# The point of the article is not WHICH facts come back — it is what mem0 DOES
# with them relative to an existing, contradicting memory. That behavior lives
# in mem0's pipeline, not here.
class StubLLM:
    def __init__(self, *a, **k):
        self._queue = []
    def enqueue(self, obj):
        import json
        self._queue.append(json.dumps(obj))
    def generate_response(self, messages, response_format=None, **kwargs):
        return self._queue.pop(0)

# --- Stub embedder: deterministic vectors, no network. Vectors only affect
#     retrieval ordering here, not the add/update/delete decision. ---
class StubEmbedder:
    def _vec(self, text):
        h = abs(hash(text))
        return [((h >> (i * 3)) & 7) / 7.0 for i in range(DIM)]
    def embed(self, text, memory_action=None):
        if isinstance(text, list):
            text = " ".join(text)
        return self._vec(text)
    def embed_batch(self, texts, memory_action=None):
        return [self._vec(t) for t in texts]

d = tempfile.mkdtemp()
cfg = MemoryConfig()
cfg.vector_store = VectorStoreConfig(
    provider="qdrant",
    config={"path": os.path.join(d, "q"), "collection_name": "demo",
            "embedding_model_dims": DIM, "on_disk": False},
)
m = Memory(cfg)
m.llm = StubLLM()
m.embedding_model = StubEmbedder()

USER = "alex"

# Turn 1: a clear preference.
m.llm.enqueue({"memory": [{"text": "User loves cheese pizza"}]})
r1 = m.add("I absolutely love cheese pizza.", user_id=USER)
print("add #1 events:", [(e["memory"], e["event"]) for e in r1["results"]])

# Turn 2: the user directly contradicts turn 1 and adds a new fact.
m.llm.enqueue({"memory": [
    {"text": "User no longer eats cheese pizza"},
    {"text": "User became vegan"},
]})
r2 = m.add("Actually I stopped eating cheese pizza — I went vegan.", user_id=USER)
print("add #2 events:", [(e["memory"], e["event"]) for e in r2["results"]])

# What is in memory now?
all_mem = m.get_all(filters={"user_id": USER})["results"]
print("\nStored memories after the contradiction (sorted):")
for mem in sorted(all_mem, key=lambda x: x["memory"]):
    print("  -", mem["memory"])

# Every history event mem0 recorded, by type:
from collections import Counter
all_events = []
for mem in all_mem:
    all_events += [h["event"] for h in m.history(mem["id"])]
print("\nHistory event types across all memories:", dict(Counter(all_events)))

m.vector_store.client.close()  # clean shutdown of the embedded Qdrant client
