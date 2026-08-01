"""virtual_mode=True (the 0.7.0 default) sandboxes the on-disk backend under root_dir."""
import tempfile, pathlib
from deepagents.backends import FilesystemBackend

root = pathlib.Path(tempfile.mkdtemp())
fs = FilesystemBackend(root_dir=root)     # virtual_mode defaults to True in 0.7.x
print("virtual_mode default:", fs.virtual_mode)

# A "/etc/passwd" write is treated as a VIRTUAL absolute path, anchored under root_dir.
fs.write("/etc/passwd", "not the real one\n")
landed = root / "etc" / "passwd"
print("wrote /etc/passwd ->", landed)
print("real /etc/passwd untouched:", pathlib.Path("/etc/passwd").read_text().splitlines()[0][:12], "...")

# A path that tries to escape the root is rejected outright.
try:
    fs.write("/../escape.txt", "trying to break out\n")
except ValueError as e:
    print("traversal attempt ->", type(e).__name__, str(e))
