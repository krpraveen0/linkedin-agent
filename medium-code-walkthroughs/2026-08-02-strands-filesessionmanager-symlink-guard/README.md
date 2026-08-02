# Strands `FileSessionManager` symlink & path-traversal guards — code walkthrough

Companion code for the article **"Strands Agents Writes Your Agent's Memory to Disk as JSON. Version 1.48 Stopped It From Following a Symlink to Get There."**

These three scripts demonstrate, with no model, no API key, and no AWS account, the two guards that protect Strands' file-backed session store:

1. `_identifier.validate` — rejects any `session_id`/`agent_id` containing a path separator.
2. The `os.path.islink` refusal added in `strands-agents` 1.48.0 (2026-07-17) — refuses to read or write through a symlink.

## Setup

Two virtualenvs: the current release, and the pre-fix release used as a control.

```bash
python3 -m venv sv      && ./sv/bin/pip install "strands-agents==1.50.2"
python3 -m venv sv_old  && ./sv_old/bin/pip install "strands-agents==1.47.0"
```

## Run

### 1. Path-separator rejection (current release)

```bash
./sv/bin/python demo1_path_traversal.py
```

Real captured output (temp-dir hash will differ on your machine):

```
normal  -> /tmp/strands_store_0negcy4i/session_chat-001
rejected -> '../../etc/evil': session_id=../../etc/evil | id cannot contain path separators
rejected -> 'a/b': session_id=a/b | id cannot contain path separators
rejected -> '/etc/passwd': session_id=/etc/passwd | id cannot contain path separators
rejected -> 'chat/../../../root': session_id=chat/../../../root | id cannot contain path separators
passes validate -> '.' maps to '/tmp/strands_store_0negcy4i/session_.'
passes validate -> '..' maps to '/tmp/strands_store_0negcy4i/session_..'
```

The two `passes validate` lines are the subtlety: `.` and `..` slip past the
`os.path.basename(id) != id` check, but the `session_` prefix turns them into
harmless literal directory names (`session_.`, `session_..`), not traversal.

### 2. Symlink read + write refusal (current release)

```bash
./sv/bin/python demo2_symlink_read_write.py
```

Real captured output:

```
real read OK -> chat-001
read refused -> Refusing to read symlink at /tmp/strands_store_l77niqkv/session_chat-001/session.json. This may indicate a symlink attack or session tampering.
write refused -> Refusing to write to symlink at /tmp/strands_store_l77niqkv/session_chat-001/session.json. This may indicate a symlink attack.
outside.json created? False
```

### 3. Old vs new — the fix in action

Run the same symlink-swap script under both versions:

```bash
echo "### strands 1.47.0 (pre-fix):" && ./sv_old/bin/python demo3_old_vs_new.py
echo "### strands 1.50.2 (current):" && ./sv/bin/python demo3_old_vs_new.py
```

Real captured output:

```
### strands 1.47.0 (pre-fix):
read FOLLOWED the symlink -> session_id = INJECTED
### strands 1.50.2 (current):
read refused -> Refusing to read symlink at /tmp/strands_store_qzv_3i4a/session_chat-001/session.json. This may indicate a symlink attack or session tampering.
```

Under 1.47.0 the agent loads attacker-chosen state (`INJECTED`); under 1.50.2
the read is refused before `open()` runs.

## Caveat

The read-side `islink` check and the subsequent `open()` are separate,
non-atomic operations — a genuine time-of-check-to-time-of-use (TOCTOU) window.
The guard defeats a symlink already sitting in the session directory; it does
not make a shared, attacker-writable session directory safe. Keep the session
store on a private path (Strands defaults to `~/.strands/sessions/`, mode
`0o700`).

## Verified environment

- Python 3.11
- `strands-agents==1.50.2` (current) and `==1.47.0` (control)
- All output above was captured from real runs; behavior confirmed by direct
  inspection of `strands/session/file_session_manager.py` and
  `strands/_identifier.py` in the installed package.
