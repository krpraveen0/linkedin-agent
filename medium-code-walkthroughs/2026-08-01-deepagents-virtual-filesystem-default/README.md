# deepagents 0.7: where does `write_file` actually write?

Runnable code for the 2026-08-01 Medium article. Three short scripts demonstrate,
against the real installed `deepagents==0.7.1` package, that:

1. `virtual_mode` defaults to `True` on both disk-capable backends, and a
   no-backend `FilesystemMiddleware` falls back to `StateBackend`.
2. The default `StateBackend` stores `write_file` output in LangGraph agent
   state (the `files` key) — nothing hits your disk.
3. With `virtual_mode=True`, `FilesystemBackend` anchors model-supplied absolute
   paths under `root_dir` and rejects `..`/`~` traversal.

No API key or hosted model is required — `demo_state.py` drives a real
`create_deep_agent` graph with a scripted fake chat model.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install "deepagents==0.7.1"
```

## Run

```bash
python demo_defaults.py
python demo_state.py
python demo_virtual.py
```

## Captured output

These are the real outputs captured on 2026-08-01 with `deepagents==0.7.1`,
Python 3.11.15. The timestamp in `demo_state.py` and the `/tmp/tmpXXXX` path in
`demo_virtual.py` vary per run; everything else is stable.

### `demo_defaults.py`

```
deepagents: 0.7.1
FilesystemBackend.virtual_mode default = True
LocalShellBackend.virtual_mode default = True
no-backend middleware -> StateBackend
```

### `demo_state.py`

```
files key in returned state: ['/reports/summary.md']
content stored in state    : {'content': 'quarterly numbers look fine\n', 'encoding': 'utf-8', 'created_at': '2026-08-01T00:40:42.885321+00:00', 'modified_at': '2026-08-01T00:40:42.885321+00:00'}
exists on real disk?       : False
```

### `demo_virtual.py`

```
virtual_mode default: True
wrote /etc/passwd -> /tmp/tmpu2byd68k/etc/passwd
real /etc/passwd untouched: root:x:0:0:r ...
traversal attempt -> ValueError Path traversal not allowed
```

## Files

- `demo_defaults.py` — reads the two defaults off the installed package.
- `demo_state.py` — end-to-end `create_deep_agent` run with a fake model.
- `demo_virtual.py` — `virtual_mode` path anchoring and traversal rejection.
- `article.md` — the full article.
- `diagram-1-backend-routing.svg`, `diagram-2-virtual-mode.svg` — figures.

## Sources

- deepagents CHANGELOG (0.7.0, 2026-07-29; 0.7.1, 2026-07-30): https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/CHANGELOG.md
- StateBackend source: https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/state.py
- FilesystemBackend source: https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/filesystem.py
