# Strands Agents Writes Your Agent's Memory to Disk as JSON. Version 1.48 Stopped It From Following a Symlink to Get There.

When you give a [Strands](https://strandsagents.com/) agent a `session_id` and no database, it does the obvious thing: it writes the conversation to your local filesystem as plain JSON, one file per message, under `~/.strands/sessions/`. That is convenient for local development and for single-container deployments. It also means your agent's persisted memory is now an ordinary set of files that ordinary filesystem tricks can attack.

On July 17, 2026, the Strands Python SDK shipped a one-line-titled commit into version 1.48.0: `fix(session): prevent symlink attacks in FileSessionManager` (from the [python/v1.48.0 release notes](https://github.com/strands-agents/sdk-python/releases/tag/python%2Fv1.48.0), released per [PyPI](https://pypi.org/project/strands-agents/) on that date). The current release as of this writing is 1.50.2, from July 27, 2026. This article is about what that guard actually does, what a second, older guard next to it does, and — because a symlink check is a check-then-use pattern — what it still can't promise. Every behavior below was verified by inspecting and running the installed `strands-agents==1.50.2` package, with `1.47.0` as the pre-fix control.

## Where the files live, and why that's the attack surface

Strands is [AWS's open-source, model-driven agent SDK](https://strandsagents.com/); the Python SDK reached 1.0 in May 2026. Its `FileSessionManager` is the zero-dependency persistence backend. Point an agent at it and you get this tree on disk:

```
<storage_dir>/
└── session_<session_id>/
    ├── session.json
    └── agents/
        └── agent_<agent_id>/
            ├── agent.json
            └── messages/
                └── message_0.json
```

Two facts from the source (`strands/session/file_session_manager.py`) matter here. First, the default storage directory is `~/.strands/sessions/`, created with mode `0o700`; the docstring explicitly notes this "avoids the world-writable `/tmp` directory." Second, every path is built by string-concatenating a caller-supplied id after a fixed prefix: `session_<session_id>`, `agent_<agent_id>`, `message_<int>.json`. A caller-supplied string that lands inside a filesystem path is exactly the shape of a path-traversal bug — unless something validates it. Two somethings do.

## Guard one: a `session_id` cannot contain a path separator

Every session and agent id passes through `strands/_identifier.py` before it becomes a path. The whole check is four lines:

```python
def validate(id_: str, type_: Identifier) -> str:
    if os.path.basename(id_) != id_:
        raise ValueError(f"{type_.value}_id={id_} | id cannot contain path separators")
    return id_
```

The trick is `os.path.basename(id_) != id_`. For any string that contains a `/`, `basename` returns only the last segment, so it no longer equals the original and the check fires. `"../../etc/evil"` → basename `"evil"` → rejected. `"a/b"` → rejected. `"/etc/passwd"` → rejected. A clean id like `"chat-001"` is its own basename, so it passes.

There is a subtlety worth knowing, because it looks like a hole and isn't. The strings `"."` and `".."` *pass* this check — `os.path.basename("..")` is `".."`, which equals itself. What saves you is the prefix: the id is never used bare. `".."` becomes the directory name `session_..`, a literal folder called "session_.." — not the parent directory. The prefix neutralizes the one case the basename check lets through. This guard, incidentally, already existed in 1.47.0; it is not the July 17 fix.

## Guard two: refuse to follow a symlink (this is the 1.48 fix)

Validating the id stops an attacker from *naming* a path outside the store. It does nothing about a symlink *planted at a legitimate path*. Suppose your agent will write `session_chat-001/session.json`, and a local attacker (or a buggy sibling process sharing the directory) replaces that file with a symlink pointing at `/home/you/.bashrc`. A naive `open(path, "w")` follows the link and truncates your shell config. A naive `open(path)` for reading hands the attacker's chosen content back to your agent as if it were trusted session state.

The 1.48 fix adds an explicit refusal at both ends. Reads:

```python
def _read_file(self, path: str) -> dict[str, Any]:
    # Refuse to read through symlinks (prevents session data injection)
    if os.path.islink(path):
        raise SessionException(
            f"Refusing to read symlink at {path}. "
            "This may indicate a symlink attack or session tampering."
        )
    with open(path, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))
```

Writes get the same `islink` refusal, plus an atomic-write pattern: the data goes to a `tempfile.mkstemp()` file with an unpredictable name in the same directory, then `os.replace()` renames it over the target. `os.replace` renames rather than opening through the destination, so it does not follow a symlink at the target path — the `islink` check on the write side is belt-and-suspenders on top of an already rename-based write. On the read side, `open()` genuinely does follow symlinks, so there the `islink` check is the load-bearing guard.

## Try It Yourself

Everything here runs locally with no model, no API key, and no AWS account. Install the SDK into a fresh virtualenv:

```bash
python -m venv sv && ./sv/bin/pip install "strands-agents==1.50.2"
```

**Path-separator rejection.** This calls the real path-building method with hostile ids and shows the `.`/`..` edge case:

```python
import tempfile
from strands.session.file_session_manager import FileSessionManager
from strands._identifier import validate, Identifier

store = tempfile.mkdtemp(prefix="strands_store_")
mgr = FileSessionManager(session_id="chat-001", storage_dir=store)
print("normal  ->", mgr._get_session_path("chat-001"))

for bad in ["../../etc/evil", "a/b", "/etc/passwd", "chat/../../../root"]:
    try:
        mgr._get_session_path(bad)
        print(f"ACCEPTED (bad!) -> {bad!r}")
    except ValueError as e:
        print(f"rejected -> {bad!r}: {e}")

for edge in [".", ".."]:
    validate(edge, Identifier.SESSION)   # does NOT raise
    print(f"passes validate -> {edge!r} maps to {mgr._get_session_path(edge)!r}")
```

Real output:

```
normal  -> /tmp/strands_store_0negcy4i/session_chat-001
rejected -> '../../etc/evil': session_id=../../etc/evil | id cannot contain path separators
rejected -> 'a/b': session_id=a/b | id cannot contain path separators
rejected -> '/etc/passwd': session_id=/etc/passwd | id cannot contain path separators
rejected -> 'chat/../../../root': session_id=chat/../../../root | id cannot contain path separators
passes validate -> '.' maps to '/tmp/strands_store_0negcy4i/session_.'
passes validate -> '..' maps to '/tmp/strands_store_0negcy4i/session_..'
```

The two "passes validate" lines are the subtlety: the ids get through the basename check, but the `session_` prefix turns them into harmless literal directory names.

**The symlink guard, old versus new.** Constructing the manager already creates `session.json` for you. This script swaps that file for a symlink to an attacker-controlled file, then reads the session back — run it under both versions:

```python
import os, json, tempfile
from strands.session.file_session_manager import FileSessionManager
from strands.types.exceptions import SessionException

store = tempfile.mkdtemp(prefix="strands_store_")
mgr = FileSessionManager(session_id="chat-001", storage_dir=store)
session_file = os.path.join(store, "session_chat-001", "session.json")

attacker = os.path.join(store, "attacker.json")
with open(attacker, "w") as fh:
    json.dump({"session_id": "INJECTED", "session_type": "AGENT"}, fh)
os.remove(session_file)
os.symlink(attacker, session_file)   # session.json -> attacker.json

try:
    s = mgr.read_session("chat-001")
    print("read FOLLOWED the symlink -> session_id =", s.session_id)
except SessionException as e:
    print("read refused ->", str(e).splitlines()[0])
```

Running it against the pre-fix and current releases gives the byte-for-byte contrast:

```
### strands 1.47.0 (pre-fix):
read FOLLOWED the symlink -> session_id = INJECTED
### strands 1.50.2 (current):
read refused -> Refusing to read symlink at /tmp/strands_store_qzv_3i4a/session_chat-001/session.json. This may indicate a symlink attack or session tampering.
```

Under 1.47.0 the agent loads `INJECTED` as its own session id — attacker-chosen state, silently trusted. Under 1.50.2 the read is refused before `open()` runs. The write path behaves the same way: planting a symlink at the target and calling `_write_file` raises `Refusing to write to symlink...`, and the file the symlink pointed at is never created.

## What it still can't promise

Be precise about the guarantee. `_read_file` does `os.path.islink(path)` and then, on a separate line, `open(path)`. That is a check-then-use sequence, and the two operations are not atomic. A local attacker who can race the process could pass the `islink` check with a real file and swap in a symlink before `open()` runs — the classic time-of-check-to-time-of-use (TOCTOU) window. The guard raises the bar substantially: it defeats a symlink that is already sitting there when your agent starts, which is the realistic case for a stale or tampered session directory. It does not turn a shared, attacker-writable session directory into a safe one. The durable fix for that is the same as it has always been: don't let untrusted users write into your agent's session directory, and keep the default `0o700` permissions Strands gives you. The write path is on firmer ground, because `os.replace()` is a rename and never opens through the destination link.

None of this requires you to change your code. If you already use `FileSessionManager`, upgrading past 1.48.0 gets you the guard for free. What's worth doing deliberately is the second half: treat the session directory as security-sensitive storage, not scratch space.

## Key Takeaways

- Strands' `FileSessionManager` persists agent state as plain JSON under `~/.strands/sessions/` (mode `0o700` by default), which makes the files a real, if modest, attack surface.
- Two independent guards protect it: a path-separator check on every id (`os.path.basename(id) != id`), and — new in 1.48.0 (2026-07-17) — an `os.path.islink` refusal on both read and write.
- The path check lets `"."` and `".."` through, but the `session_`/`agent_` prefix makes them inert directory names rather than traversal.
- The symlink read guard has an inherent TOCTOU window; it stops a pre-planted symlink, not a determined local attacker racing the process. The write guard is stronger because it renames rather than opens through the target.
- The fix is transparent: upgrade and you get it. The part that needs your judgment is keeping the session directory off shared, writable paths.

**Sources:** [Strands Agents](https://strandsagents.com/) · [python/v1.48.0 release notes](https://github.com/strands-agents/sdk-python/releases/tag/python%2Fv1.48.0) · [strands-agents on PyPI](https://pypi.org/project/strands-agents/) · direct inspection of `strands/session/file_session_manager.py` and `strands/_identifier.py` in the installed `strands-agents==1.50.2` package, with `1.47.0` as the pre-fix control.
