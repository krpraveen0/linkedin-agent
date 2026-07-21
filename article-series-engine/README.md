# Article Series Engine

**This directory is fully separate from `aep/`.** It does not share pipelines,
policies, schemas, prompts, workflows, or publishing conventions with AEP.
Nothing here reads from or writes to `aep/**`, and nothing in `aep/` should
read from or write to `article-series-engine/**`. Two independent systems,
intentionally kept apart.

## What this is

A manifest-driven pipeline for a Medium-publish-ready article series,
"Design Multi-Agent Systems." The manifest (article list, status, the
specific competitive gap each article closes) lives in Notion, not in this
repo. This folder holds only the runnable code and diagrams for each
article, organized by series and article number.

## Structure

```
series/
  multi-agent-systems-design/
    article-01-multi-agent-or-overkill/
      src/
      diagrams/
      assets/
    article-02-.../
    ...
```

## Workflow

Each article's code is developed on its own branch
(`series/multi-agent-systems-design/article-NN`) and merged via PR after
manual review — no auto-merge, same as the Medium side isn't
auto-published. See the Notion manifest for article-by-article status.
