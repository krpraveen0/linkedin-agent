# mini-project: MCP tool calling, with a mock customized-model decision step

Demonstrates the mechanics this article is about: an agent that (1) asks a
tool-calling model which MCP tool applies to a user message, then (2) invokes
that tool on a real MCP server over the STDIO transport, using the actual
JSON-RPC 2.0 message shapes from the MCP spec.

`tool_calling_model.py` is a **deterministic, rule-based stand-in** for the
customized model this article discusses hosting on a serverless Amazon
SageMaker AI endpoint — see the module docstring for why (no AWS
account/billing available in this repo's sandbox). Swapping that one module
for a real `boto3` / `sagemaker-runtime` `invoke_endpoint` call, keeping the
same `{name, arguments}` return shape, is the only change needed to go from
this demo to the real architecture in `../article.md`.

## Files

- `mcp_tools_server.py` — MCP server exposing two tools (`get_order_status`,
  `convert_currency`) over STDIO.
- `tool_calling_model.py` — stand-in for the SageMaker-hosted tool-calling
  model's decision step.
- `mcp_agent.py` — orchestrator: spawns the server, discovers tools via
  `tools/list`, runs the decision step per sample message, calls `tools/call`,
  and prints the JSON-RPC exchange plus a synthesized answer.

## Requirements

Python 3.10+ (uses `dict | None` union syntax), standard library only — no
`pip install` needed.

## Run it

```bash
cd project
python3 mcp_agent.py
```

## Execution status

**Verified.** The authoring session's sandbox blocked all local command
execution (`python3` returned `This command requires approval` with no
interactive user available to grant it), so the code was traced but not run
at authoring time — see `build-artifact.json`'s original `generated_at`
entry for that honest disclosure. A follow-up review, outside that sandbox,
ran it for real:

```
$ python3 mcp_agent.py
[initialize] -> {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25", "serverInfo": {"name": "support-tools", "version": "0.1.0"}}}
[tools/list] -> 2 tools: ['get_order_status', 'convert_currency']

User: What's the status of order A1001?
  tool-calling model decided -> {"name": "get_order_status", "arguments": {"order_id": "A1001"}}
  [tools/call] -> {"jsonrpc": "2.0", "id": 3, "result": {"status": "shipped", "carrier": "UPS", "eta_days": 2}}
Agent: your order is shipped via UPS, ETA 2 day(s).

User: Can you convert 100 USD to EUR?
  tool-calling model decided -> {"name": "convert_currency", "arguments": {"amount": 100.0, "from_currency": "USD", "to_currency": "EUR"}}
  [tools/call] -> {"jsonrpc": "2.0", "id": 4, "result": {"converted_amount": 92.59, "to_currency": "EUR"}}
Agent: that's 92.59 EUR.

User: What's the weather like today?
Agent: no tool matched this message; would fall back to a direct model answer.
```

Full output also saved at `evidence/run-mcp_agent.log` (`exit_code=0`). One
correction made in the process: `mcp_tools_server.py`'s `protocolVersion` was
`2025-06-18` (stale) at authoring time, bumped to `2025-11-25` (current
stable MCP spec — the `2026-07-28` revision is a release candidate, not yet
final). `build-artifact.json`'s `build_status` now reflects this real run.
