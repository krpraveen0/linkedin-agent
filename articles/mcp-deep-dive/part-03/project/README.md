# MCP two-tier error-handling demo

Demonstrates the distinction from [SEP-1303](https://modelcontextprotocol.io/seps/1303-input-validation-errors-as-tool-execution-errors)
("Input Validation Errors as Tool Execution Errors", status: Final):

- An **unknown tool or method** is a JSON-RPC **Protocol Error** — the MCP
  client handles it; the calling model never sees it.
- **Invalid tool arguments** (here: a malformed or past-dated
  `departureDate`) are a **Tool Execution Error** — a normal JSON-RPC
  result with `isError: true`, which *is* forwarded into the model's
  context, so the model can read the reason and retry with a corrected
  argument.

No dependencies — Python 3 standard library only (`json`, `re`,
`datetime`).

## Run it

```bash
python3 mcp_error_handling_server.py
```

This runs three scenarios through `handle_request()` end to end and
asserts the response shape for each: an unknown tool, a past-dated
argument, and a valid future date. It prints `PASS`/`FAIL` per scenario
plus the raw request/response JSON, and exits `0` only if all three
assertions hold.

## Execution status

**Verified by CI, not yet by a captured local transcript.** Every
authoring/audit-loop session so far has had Bash access to `python3`
blocked beyond `--version` (any other form — `-c`, running a `.py` file —
requires an approval with no interactive user available to grant it,
confirmed directly and via a fresh subagent). The logic was traced by
hand at authoring time — see `article.md`'s Mini-project section for the
scenario-by-scenario trace.

Real evidence comes from CI instead: `aep-article-check.yml` →
`validate_article.py`'s `check_execution` independently
`subprocess.run()`s the command above for real, inside an unrestricted
GitHub Actions runner, on every push to this PR — that check is not
gated by any sandbox here. Run
[29933532865](https://github.com/krpraveen0/linkedin-agent/actions/runs/29933532865)
(job `88969094053`, commit `b34dddac5dce9b2b6a7ce1b4c6127fd623cb8355`)
reported zero execution failures, which `check_execution`'s contract
only allows if the real subprocess exited `0` — see
[`evidence/check_execution-ci-verification.md`](evidence/check_execution-ci-verification.md)
for the full reasoning. `validate_article.py` doesn't print the
subprocess's stdout on a passing run, so no raw `[PASS]`/`[FAIL]`
transcript is captured yet; a human running the one command above
locally would produce one in seconds and can update this section and
`build-artifact.json`'s `evidence_path` accordingly.
