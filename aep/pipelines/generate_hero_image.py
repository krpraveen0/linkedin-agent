#!/usr/bin/env python3
"""Generate a hero/cover image for an article without any external API call.

matplotlib is the only sanctioned image path under aep/policies/no-external-llm-policy.md
(it renders locally from code — no network call, no LLM/image-gen provider). This gives
every article a real hero image by default; an agent may replace it with a hand-authored
SVG/PNG if it wants something more polished, but nothing should ship without one.
"""
import argparse
import pathlib
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def generate(title: str, kicker: str, out_path: pathlib.Path, width: int = 1200, height: int = 630) -> None:
    dpi = 100
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, facecolor="#0d1117", edgecolor="none"))
    ax.add_patch(mpatches.Rectangle((0, 0), 1, 0.06, facecolor="#2f81f7", edgecolor="none"))
    for i, x in enumerate([0.08, 0.14, 0.2]):
        ax.add_patch(mpatches.Circle((x, 0.9), 0.012, facecolor="#2f81f7", alpha=0.6 - i * 0.15))

    ax.text(0.07, 0.78, kicker.upper(), fontsize=13, color="#2f81f7", weight="bold", family="monospace")

    wrapped = textwrap.fill(title, width=28)
    ax.text(0.07, 0.55, wrapped, fontsize=30, color="#f0f6fc", weight="bold", va="top", family="sans-serif")

    ax.text(0.07, 0.1, "EngineeringCoders — AEP", fontsize=11, color="#8b949e", family="monospace")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor="#0d1117", bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a code-rendered hero image (no external API).")
    parser.add_argument("--title", required=True)
    parser.add_argument("--kicker", default="engineering deep dive")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    generate(args.title, args.kicker, args.out)
    print(f"hero image written: {args.out}")


if __name__ == "__main__":
    main()
