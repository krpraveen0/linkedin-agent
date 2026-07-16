#!/usr/bin/env python3
"""Reduce a list of changed articles/** file paths to the article folders that
own them, for aep-article-check.yml to validate. One path per line on stdin.

- articles/<series>/part-XX/... -> articles/<series>/part-XX
- articles/<slug>/...           -> articles/<slug>
- articles/<series>/README.md alone (no article.md/publish-draft.json in that
  folder, and it has part-* subfolders) is a series index, not an article ->
  skipped, since editing just the index shouldn't fail the readiness gate.
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def reduce_to_article_dir(rel_path: str) -> str | None:
    parts = pathlib.PurePosixPath(rel_path).parts
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and parts[2].startswith("part-"):
        return str(pathlib.PurePosixPath(*parts[:3]))
    return str(pathlib.PurePosixPath(*parts[:2]))


def is_series_index_only(dir_rel: str) -> bool:
    d = REPO_ROOT / dir_rel
    if (d / "article.md").exists() or (d / "publish-draft.json").exists():
        return False
    return any(p.is_dir() and p.name.startswith("part-") for p in d.glob("part-*"))


def main() -> None:
    seen: list[str] = []
    for line in sys.stdin:
        rel_path = line.strip()
        if not rel_path:
            continue
        dir_rel = reduce_to_article_dir(rel_path)
        if dir_rel is None or dir_rel in seen:
            continue
        if is_series_index_only(dir_rel):
            continue
        seen.append(dir_rel)
    for d in seen:
        print(d)


if __name__ == "__main__":
    main()
