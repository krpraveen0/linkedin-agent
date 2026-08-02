"""Demo 1: FileSessionManager rejects session IDs that contain path separators."""
import tempfile
from strands.session.file_session_manager import FileSessionManager
from strands._identifier import validate, Identifier

store = tempfile.mkdtemp(prefix="strands_store_")
mgr = FileSessionManager(session_id="chat-001", storage_dir=store)

# A normal id maps to a directory *inside* the storage dir.
print("normal  ->", mgr._get_session_path("chat-001"))

# Attacker-controlled ids that try to escape the storage dir.
for bad in ["../../etc/evil", "a/b", "/etc/passwd", "chat/../../../root"]:
    try:
        mgr._get_session_path(bad)
        print(f"ACCEPTED (bad!) -> {bad!r}")
    except ValueError as e:
        print(f"rejected -> {bad!r}: {e}")

# The check is os.path.basename(id) != id. Show the two ids it still lets pass,
# and why the SESSION_PREFIX makes them harmless.
for edge in [".", ".."]:
    validate(edge, Identifier.SESSION)            # does NOT raise
    print(f"passes validate -> {edge!r} maps to {mgr._get_session_path(edge)!r}")
