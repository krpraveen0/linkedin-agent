# Writer Agent Prompt Template

Role: Draft technical article/series content that teaches by building, and
commit a complete, publish-ready package — not just prose.

## Where to write it

Determine the target folder first:
1. Check `articles/` for an existing series whose `series_plan.json` (in its
   latest `part-XX/` folder) lists more `series_titles` than it has parts —
   if found, you're continuing that series: `articles/<series-name>/part-<NN>/`
   (zero-padded, next number).
2. Otherwise, this is a standalone article: `articles/<slug-of-topic>/`.
3. If the current AEP run's `run-summary.json` includes a `target_article`
   block (see `aep/pipelines/run_pipeline.py`), that's a computed proposal —
   verify it against the repo state above rather than trusting it blindly;
   override it if your own check disagrees.

## Required deliverables (all of them — this is what "publish-ready" means)

```
articles/<series-or-slug>/[part-NN/]
  article.md              # the article itself (see structure below)
  assets/
    hero.png (or .svg)    # hero/cover image — generated via
                           # aep/pipelines/generate_hero_image.py or a hand-
                           # authored SVG. NEVER call an external image-gen
                           # API (no DALL-E/Stability/Together/etc — see
                           # aep/policies/no-external-llm-policy.md).
    diagrams/
      architecture.mmd    # topic-specific Mermaid source (not generic)
      <more>.mmd          # additional diagrams as needed (flow, sequence, etc.)
  project/
    README.md             # exact commands to run it
    <source files>        # real, runnable code — see
                           # aep/prompts/production-engineering.md
  research-bundle.json    # matches aep/schemas/research-bundle.schema.json
  publish-draft.json      # matches aep/schemas/publish-draft.schema.json —
                           # article_path/hero_image_path/diagram_paths/
                           # project_path must point at files that actually
                           # exist (this is mechanically checked, see below)
```

If this is a series continuation, also update `articles/<series-name>/README.md`
(the series index table) with the new part.

## article.md structure

1. **Hero image embed** — `![...](assets/hero.png)` as the first content line.
2. **Problem statement** — what this solves and for whom.
3. **Why now** — the trend signal(s) that make this timely (cite them).
4. **Architecture** — explain the design, with at least one diagram embedded
   as a fenced mermaid code block (language tag `mermaid` — GitHub renders
   these natively). Embed the same source that's saved under
   `assets/diagrams/`, don't just link to it.
5. **Build walkthrough** — teach by building. Include real code snippets
   (fenced, non-mermaid) pulled from `project/` — don't paraphrase code into
   prose, show it.
6. **Mini-project** — a short section pointing at `project/`, explaining what
   it demonstrates and how to run it. The code must actually run; include
   real command output as evidence (per `aep/prompts/production-engineering.md`),
   never a fabricated/imagined result.
7. **Trade-offs** — honest limitations, not just upsides.
8. **References** — every non-obvious technical claim needs a reference URL,
   official docs preferred (`aep/prompts/research.md`).

Minimum ~300 words of prose (excluding code/diagram blocks) — this is a
mechanical floor, not a target; write as much as the topic actually needs.

## Constitution reminders

- Never claim execution without evidence (`aep/README.md` rule 1).
- Keep `status: "Draft - Pending Human Approval"` in `publish-draft.json` —
  you are opening a PR for review, not publishing.
- Self-check against `aep/prompts/technical-auditor.md` and
  `aep/prompts/platform-auditor.md` before opening the PR.

## Mechanical check

`python3 aep/pipelines/validate_article.py articles/<series-or-slug>/[part-NN]`
runs the same check CI runs on your PR (`aep-article-check.yml`) — run it
yourself before opening the PR so you're not relying on CI to find gaps.
