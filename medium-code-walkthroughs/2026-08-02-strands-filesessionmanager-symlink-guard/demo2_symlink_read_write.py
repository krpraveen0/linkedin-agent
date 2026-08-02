"""Demo 2: FileSessionManager refuses to read or write through a symlink."""
import os, json, tempfile
from strands.session.file_session_manager import FileSessionManager
from strands.types.exceptions import SessionException

store = tempfile.mkdtemp(prefix="strands_store_")
# Constructing the manager creates session_chat-001/session.json for us.
mgr = FileSessionManager(session_id="chat-001", storage_dir=store)
session_file = os.path.join(store, "session_chat-001", "session.json")
print("real read OK ->", mgr.read_session("chat-001").session_id)

# Attacker swaps the session file for a symlink to a file they control.
attacker = os.path.join(store, "attacker.json")
with open(attacker, "w") as f:
    json.dump({"session_id": "chat-001", "session_type": "AGENT"}, f)
os.remove(session_file)
os.symlink(attacker, session_file)   # session.json -> attacker.json

try:
    mgr.read_session("chat-001")
    print("READ FOLLOWED SYMLINK (bad!)")
except SessionException as e:
    print("read refused ->", str(e).splitlines()[0])

# Write side: plant a symlink at the target path pointing outside the store,
# then attempt a write and check whether the outside file was created.
os.remove(session_file)
target = os.path.join(store, "outside.json")
os.symlink(target, session_file)
try:
    mgr._write_file(session_file, {"pwned": True})
    print("WRITE FOLLOWED SYMLINK (bad!) -> outside.json exists:", os.path.exists(target))
except SessionException as e:
    print("write refused ->", str(e).splitlines()[0])
    print("outside.json created?", os.path.exists(target))
