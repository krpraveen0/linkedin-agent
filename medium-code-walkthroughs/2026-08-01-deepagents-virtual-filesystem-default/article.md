# deepagents 0.7: Your Agent's `write_file` Never Touches Disk by Default — and the One Backend That Does Just Got Sandboxed

You hand a `deepagents` agent a task, watch it call `write_file("/reports/summary.md", ...)`, and the run finishes clean. Then you go looking for `summary.md` on your machine. It isn't there. Not in your working directory, not at `/reports/`, nowhere. The file the agent said it wrote does not exist on disk.

That is not a bug. It is the default, and as of [deepagents 0.7.0 (released 29 July 2026)](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/CHANGELOG.md) the behavior of the *other* backend — the one that genuinely writes to disk — changed too. If you build on this library, both defaults are worth understanding before you ship, because they decide whether your agent's file operations are a harmless scratchpad or a hole in your host filesystem.

## What deepagents is, in one paragraph

[Deep Agents](https://www.marktechpost.com/2026/03/15/langchain-releases-deep-agents-a-structured-runtime-for-planning-memory-and-context-isolation-in-multi-step-ai-agents/) is LangChain's "agent harness" — a library built on the LangGraph runtime that packages the moving parts a long-running agent needs: a planning tool (`write_todos`), subagents for context isolation, and a set of filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`) the model can call to offload bulky context out of the prompt window and pick it back up later. Those filesystem tools are the subject here. The question is simple and the answer is not obvious: when the model calls `write_file`, where does the byte actually go?

## The default backend writes to state, not disk

Every filesystem operation in deepagents is routed through a *backend*. The `FilesystemMiddleware` — the piece that installs the file tools — picks one for you if you don't pass anything. You can read the fallback straight off the installed package:

```python
import inspect
import deepagents
from deepagents.backends import FilesystemBackend, StateBackend, LocalShellBackend

print("deepagents:", deepagents.__version__)

for cls in (FilesystemBackend, LocalShellBackend):
    default = inspect.signature(cls.__init__).parameters["virtual_mode"].default
    print(f"{cls.__name__}.virtual_mode default = {default}")

from deepagents.middleware.filesystem import FilesystemMiddleware
mw = FilesystemMiddleware()          # backend=None
print("no-backend middleware ->", type(mw.backend).__name__)
```

Running it against `deepagents==0.7.1`:

```
deepagents: 0.7.1
FilesystemBackend.virtual_mode default = True
LocalShellBackend.virtual_mode default = True
no-backend middleware -> StateBackend
```

That last line is the one that surprises people. With no `backend=` argument, the middleware instantiates a [`StateBackend`](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/state.py). Its own module docstring describes exactly what that means: it stores files "in LangGraph agent state (ephemeral)," where they "persist within a conversation thread but not across threads," applied as channel writes to the `files` state key. There is no path on your host involved at all.

## Proving it end to end — without an API key

You do not need a real model to see this. You can script a fake chat model that emits one `write_file` tool call, run the actual agent graph, and inspect the resulting state. The tool's input schema is just `file_path` (absolute) and `content`.

```python
import os
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self  # the agent binds tools; we already scripted the call

TARGET, CONTENT = "/reports/summary.md", "quarterly numbers look fine\n"
model = FakeToolModel(messages=iter([
    AIMessage(content="", tool_calls=[
        {"name": "write_file", "id": "call_1",
         "args": {"file_path": TARGET, "content": CONTENT}}]),
    AIMessage(content="Done. I wrote the summary."),
]))

agent = create_deep_agent(model=model)   # backend=None -> default StateBackend
result = agent.invoke({"messages": [{"role": "user", "content": "write the summary"}]})

print("files key in returned state:", list(result.get("files", {}).keys()))
print("content stored in state    :", repr(result["files"][TARGET]))
print("exists on real disk?       :", os.path.exists(TARGET))
```

The captured output:

```
files key in returned state: ['/reports/summary.md']
content stored in state    : {'content': 'quarterly numbers look fine\n', 'encoding': 'utf-8', 'created_at': '2026-08-01T00:40:42.885321+00:00', 'modified_at': '2026-08-01T00:40:42.885321+00:00'}
exists on real disk?       : False
```

The agent "wrote" a file to an absolute path and the byte never left process memory. It lives in `result["files"]`, a dictionary keyed by the virtual path, complete with its own `created_at`/`modified_at` metadata. `os.path.exists("/reports/summary.md")` is `False`. If your mental model was "the agent wrote a file, I can `cat` it," the default backend quietly breaks that assumption — and that is by design, because ephemeral state is exactly what you want when an untrusted model is choosing the paths.

## The backend that *does* touch disk got sandboxed in 0.7.0

Some workloads genuinely need files on disk — a code agent that runs a build, say. For that you reach for `FilesystemBackend`. Before 0.7, that backend treated the absolute paths a model produced as real absolute paths, which is a sharp edge: a model that decides to `write_file("/etc/cron.d/...", ...)` was writing to `/etc/cron.d/...`.

The 0.7.0 changelog records the change (29 July 2026):

> `FilesystemBackend` and `LocalShellBackend` now default to `virtual_mode=True` … paths resolving outside `root_dir` raise `ValueError` … Pass `virtual_mode=False` explicitly to restore the old filesystem behavior.

With `virtual_mode=True`, an absolute-looking path from the model is treated as *virtual* and anchored under the `root_dir` you gave the backend, and any `..` or `~` is rejected before it resolves. You can watch both halves happen:

```python
import tempfile, pathlib
from deepagents.backends import FilesystemBackend

root = pathlib.Path(tempfile.mkdtemp())
fs = FilesystemBackend(root_dir=root)     # virtual_mode defaults to True in 0.7.x
print("virtual_mode default:", fs.virtual_mode)

fs.write("/etc/passwd", "not the real one\n")   # a virtual path, anchored under root
landed = root / "etc" / "passwd"
print("wrote /etc/passwd ->", landed)
print("real /etc/passwd untouched:", pathlib.Path("/etc/passwd").read_text().splitlines()[0][:12], "...")

try:
    fs.write("/../escape.txt", "trying to break out\n")
except ValueError as e:
    print("traversal attempt ->", type(e).__name__, str(e))
```

Captured output:

```
virtual_mode default: True
wrote /etc/passwd -> /tmp/tmpu2byd68k/etc/passwd
real /etc/passwd untouched: root:x:0:0:r ...
traversal attempt -> ValueError Path traversal not allowed
```

A write to `/etc/passwd` landed at `<root_dir>/etc/passwd`; the real `/etc/passwd` is untouched; and an attempt to climb out with `..` raised `ValueError: Path traversal not allowed`. The [backend's own docstring](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/filesystem.py) is blunt that this is path containment, not a security sandbox — it "does not provide sandboxing or process isolation" — so pair it with real OS-level isolation for untrusted code. But the containment is on by default now, which is a meaningfully safer starting point than 0.7 shipped with before.

## Why the default flip matters right now

Two things converged in late July 2026. The default backend was already state-based, so most people running the quickstart were never writing to disk in the first place — a fact that trips up anyone debugging "where did my file go." And in the same 0.7.0 release, the disk-capable backends flipped to virtual paths by default, and `write_file` changed from erroring on an existing file to [silently replacing it](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/CHANGELOG.md). If you upgrade across the 0.6→0.7 line, both behaviors move under you: paths you thought were absolute are now anchored, and a write that used to fail loudly on a collision now overwrites.

The practical rule: decide your backend explicitly. Pass `StateBackend()` when you want a disposable scratchpad, `FilesystemBackend(root_dir=...)` when you want real files inside a fenced directory, and only reach for `virtual_mode=False` when you have a deliberate reason to let the model address your whole disk — and OS isolation around it when you do.

## Try It Yourself

```bash
python -m venv venv && source venv/bin/activate
pip install "deepagents==0.7.1"
python demo_defaults.py     # virtual_mode defaults + which backend you get for free
python demo_state.py        # write_file lands in state, not on disk
python demo_virtual.py      # virtual_mode anchors paths under root_dir and blocks ..
```

Every code block above is one of those three scripts, and the output shown is the real captured stdout — including the `/tmp/tmpu2byd68k` temp path and the timestamp, which will differ on your run. None of it calls a hosted model, so it costs nothing and runs offline.

## Key Takeaways

- In `deepagents` 0.7.1, `create_deep_agent()` with no `backend=` gives you a `StateBackend`: `write_file` stores bytes in LangGraph state under the `files` key, and nothing hits your disk.
- `StateBackend` files are ephemeral — they live within a conversation thread and vanish across threads. Don't treat them as durable storage.
- `deepagents` 0.7.0 (29 July 2026) flipped `FilesystemBackend` and `LocalShellBackend` to `virtual_mode=True` by default: model-supplied absolute paths are anchored under `root_dir`, and `..`/`~` traversal raises `ValueError`.
- `virtual_mode` is path containment, not a security sandbox — the library says so. Add OS-level isolation for untrusted code.
- The same release made `write_file` overwrite an existing file instead of erroring. Re-read your assumptions when upgrading from 0.6.
- Choose your backend explicitly rather than inheriting the default; it decides whether file ops are a scratchpad or a disk write.

**Sources:** [deepagents CHANGELOG (0.7.0, 29 Jul 2026; 0.7.1, 30 Jul 2026)](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/CHANGELOG.md) · [deepagents releases](https://github.com/langchain-ai/deepagents/releases) · [StateBackend source](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/state.py) · [FilesystemBackend source](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/backends/filesystem.py) · [LangChain Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview) · [MarkTechPost: LangChain Releases Deep Agents (15 Mar 2026)](https://www.marktechpost.com/2026/03/15/langchain-releases-deep-agents-a-structured-runtime-for-planning-memory-and-context-isolation-in-multi-step-ai-agents/) · Behavior verified against the installed `deepagents==0.7.1` package.
