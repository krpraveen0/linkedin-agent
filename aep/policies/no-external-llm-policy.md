# AEP Policy: No External LLM API Usage

## Mandatory rule
AEP components under `aep/` must not call external LLM APIs or SDKs.

## Allowed
- GitHub-native Copilot agent capabilities
- Deterministic tooling (shell/python/node) for orchestration and validation
- Notion MCP integration for draft synchronization

## Prohibited examples
- External providers/SDKs such as OpenAI, Anthropic, Gemini, Groq, Cohere, or similar
- Secrets/env vars intended for external model API auth
- Direct HTTP calls from AEP code to external LLM inference endpoints

## Enforcement
- `aep-constitution-check` workflow scans `aep/**` for disallowed provider patterns.
- Any violation fails CI for AEP changes.
