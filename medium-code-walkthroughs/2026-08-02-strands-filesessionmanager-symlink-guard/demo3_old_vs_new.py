"""Same symlink swap, run under whichever strands is installed in this venv."""
import os, json, tempfile, strands
from strands.session.file_session_manager import FileSessionManager
from strands.types.exceptions import SessionException

store = tempfile.mkdtemp(prefix="strands_store_")
mgr = FileSessionManager(session_id="chat-001", storage_dir=store)
session_file = os.path.join(store, "session_chat-001", "session.json")

# Attacker replaces session.json with a symlink to a file of their choosing.
attacker = os.path.join(store, "attacker.json")
with open(attacker, "w") as fh:
    json.dump({"session_id": "INJECTED", "session_type": "AGENT"}, fh)
os.remove(session_file)
os.symlink(attacker, session_file)

try:
    s = mgr.read_session("chat-001")
    print("read FOLLOWED the symlink -> session_id =", s.session_id)
except SessionException as e:
    print("read refused ->", str(e).splitlines()[0])
