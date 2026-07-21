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
    <slug>-infographic.png (or .svg)
                           # REQUIRED once the article enumerates 3+ comparable
                           # concepts (a features list, a comparison, a set of
                           # trade-offs, etc.) — render via
                           # aep/pipelines/generate_infographic.py instead of
                           # leaving that content as another prose bullet list.
                           # See "Concept density" below for the exact rule.
  project/
    README.md             # exact commands to run it — MUST include a
                           # `## Run it` section with a fenced ```bash block
                           # whose first line is the literal command to run
                           # (this is executed by CI, see below — not decorative)
    <source files>        # real, runnable code — see
                           # aep/prompts/production-engineering.md
  research-bundle.json    # matches aep/schemas/research-bundle.schema.json —
                           # including the competitive_scan field, see
                           # aep/prompts/research.md
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
It is not a target to hit with padding — see "Concept density" below.

## Concept density: visual over listy prose

If you're about to write a bulleted or numbered list where 3+ items each
carry their own bolded label (a features list, a set of trade-offs, a
comparison of options, primitives/components of a system), that content
belongs in a rendered infographic (`aep/pipelines/generate_infographic.py`),
not as another prose list. This is mechanically checked (see below): 3+
bold-labeled list items in `article.md` requires a second visual asset
beyond the architecture diagram. Reserve prose bullets for short, non-parallel
asides that don't warrant their own visual.

## Voice: write like the person who built this, not like a summary of it

Follow `aep/prompts/brand-voice.md` — the full rule set (banned hype words,
no fabricated persona, concrete numbers over adjectives, sentence-length
variation, honest uncertainty) lives there so the LinkedIn amplification
stage (`aep/prompts/amplify.md`) applies the same house style instead of
drifting from a second copy. A fixed subset of the banned phrases is
mechanically flagged by `check_style` (see below) and will fail the check,
but that regex list is a floor, not the full standard.

## Constitution reminders

- Never claim execution without evidence (`aep/README.md` rule 1) — and
  note that CI now actually executes `project/`'s documented run command
  (see `check_execution` in `validate_article.py`), so an execution-status
  claim that contradicts what CI observes will fail the build, not just look
  bad. If the code runs successfully, say so plainly — don't leave a stale
  "not executed" disclaimer once it's verified.
- Keep `status: "Draft - Pending Human Approval"` in `publish-draft.json` —
  you are opening a PR for review, not publishing.
- Self-check against `aep/prompts/technical-auditor.md` and
  `aep/prompts/platform-auditor.md` before opening the PR.

## Mechanical check

`python3 aep/pipelines/validate_article.py articles/<series-or-slug>/[part-NN]`
runs the same check CI runs on your PR (`aep-article-check.yml`) — run it
yourself before opening the PR so you're not relying on CI to find gaps.
