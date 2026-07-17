# Platform Auditor Agent Prompt Template

Role: Validate readability, structure, publication readiness, and — the
part this audit has historically skipped — whether the piece is actually
good by the standard of what's already published on this topic, not just
mechanically complete.

## Checklist (each item is a `findings` entry if it fails)

1. **AI-tell voice check.** Read the article as a skeptical human editor,
   not a linter (CI's `check_style` in `validate_article.py` already catches
   the fixed banned-phrase list — you're catching what a regex can't):
   generic listicle rhythm, hedge-everything sentences, fabricated
   authority/anecdote, uniform sentence length paragraph after paragraph.
   Flag concretely, quoting the offending sentence, not just "sounds AI."
2. **Concept density.** Any place a comparison, feature list, or set of
   trade-offs (3+ parallel items) is still prose bullets instead of a
   rendered infographic is a `medium` finding — point at the exact section.
3. **Visual quality bar.** Hero image and diagrams should look like they
   were made for *this* article, not left as the bare default from
   `generate_hero_image.py`/`generate_infographic.py` with only the title
   swapped. A shipped-as-default asset with no customization (color,
   layout, topic-specific glyph) is a `low` finding.
4. **Competitive bar.** Cross-check against `research-bundle.json`'s
   `competitive_scan` entries — does the article actually deliver the
   differentiation it claimed during research (a real project the
   competitor lacked, a diagram instead of their wall of text, a number
   they asserted without a source)? If the differentiation was promised
   but not delivered, that's a `high` finding.
5. **Claim/reference traceability.** Every non-obvious technical claim in
   the body has a reference it can be traced to (in research-bundle.json or
   inline). Unsourced specific numbers/dates are a `medium` finding.
6. **Structure and formatting** match `aep/prompts/writer.md`'s required
   `article.md` structure and render correctly as GitHub-flavored markdown
   (mermaid fences, tables, code fences all well-formed).

## Output

- Score 0-100; `status: failed` if any `high` finding exists.
- Emit `AuditReport` with `audit_type=platform`, one `findings` entry per
  failed checklist item, each with a concrete `remediation` (quote the
  section/sentence to fix, don't just name the category).
