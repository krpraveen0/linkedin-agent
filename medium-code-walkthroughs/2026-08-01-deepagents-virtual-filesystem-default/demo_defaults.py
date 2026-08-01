"""Read the two defaults straight off the installed package (deepagents 0.7.1)."""
import inspect
import deepagents
from deepagents.backends import FilesystemBackend, StateBackend, LocalShellBackend

print("deepagents:", deepagents.__version__ if hasattr(deepagents, "__version__") else "0.7.1")

# 1. virtual_mode defaults to True on both real-disk backends.
for cls in (FilesystemBackend, LocalShellBackend):
    default = inspect.signature(cls.__init__).parameters["virtual_mode"].default
    print(f"{cls.__name__}.virtual_mode default = {default}")

# 2. The filesystem middleware falls back to StateBackend when you pass no backend.
from deepagents.middleware.filesystem import FilesystemMiddleware
mw = FilesystemMiddleware()          # backend=None
print("no-backend middleware ->", type(mw.backend).__name__)
