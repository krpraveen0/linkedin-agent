# AEP v1 Implementation Spec (Isolated Foundation)

## Objective
Establish a safe, isolated baseline for the EngineeringCoders AEP in this repository without changing existing automation behavior.

## Architecture (v1)
- **Control plane**: GitHub Issues/PRs/Actions
- **Agent plane**: Copilot agent task prompts and contracts
- **Artifact plane**: JSON schemas + markdown outputs under `aep/`
- **Publishing plane**: Notion MCP-ready draft contracts (no direct publish automation)

## Constitution controls in v1
- Publication remains blocked behind human approval state.
- Article outputs must include executable build evidence references.
- Research references prioritize official docs.
- Diagram outputs are expected to use editable source formats in later phases.
- Claim/reference traceability fields are present in schemas.

## Phased roadmap mapping
- **Phase 1 (this change)**: repo/docs/actions/contracts/policies
- **Phase 2+**: trend/research engines and deterministic scoring
- **Phase 3+**: production-engineering + writer + diagram agents
- **Phase 4+**: technical/platform audits + publisher pipeline
- **Phase 5+**: analytics and learning loop

## Copilot agent integration notes
- Prompts in `aep/prompts/` define role responsibilities and output contracts.
- Pipelines currently emit placeholders and are safe to run repeatedly.
- Future agent invocation should be added as explicit workflow steps with auditable logs.

## Notion drafting interface
- `aep/publisher/notion-page-template.md` defines canonical sections.
- `aep/publisher/notion-mapping.json` maps AEP artifacts to notion properties/blocks.
- Sync must be idempotent using `external_id` (create if not found, update if found).
