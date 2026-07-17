#!/usr/bin/env python3
"""Generate a hero/cover image for an article without any external API call.

matplotlib is the only sanctioned image path under aep/policies/no-external-llm-policy.md
(it renders locally from code — no network call, no LLM/image-gen provider). This gives
every article a real hero image by default.

This is still a code-rendered *default*, not a substitute for a hand-authored
SVG when the topic warrants something more custom — but per
aep/prompts/platform-auditor.md's visual-quality check, shipping the bare
default with only the title swapped is a flagged finding. Use `--nodes` to
give it a topic-specific glyph (see below) rather than leaving every hero
image looking identical.
"""
import argparse
import pathlib
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
ACCENT = "#2f81f7"
TEXT = "#f0f6fc"
MUTED = "#8b949e"


def _draw_node_glyph(ax, nodes: list, x0: float = 0.62, x1: float = 0.94) -> None:
    """Draw a small left-to-right chain of labeled boxes as the topic glyph.

    `nodes` is a list of short labels, e.g. ["Agent", "Model", "MCP server"] —
    this is what makes one hero image look different from another instead of
    reusing the exact same generic box-and-arrow decoration every time.
    """
    if not nodes:
        return
    n = len(nodes)
    box_h = 0.11
    gap = 0.06
    total_h = n * box_h + (n - 1) * gap
    y = 0.5 + total_h / 2 - box_h

    for i, label in enumerate(nodes):
        y_i = y - i * (box_h + gap)
        box = mpatches.FancyBboxPatch(
            (x0, y_i), x1 - x0, box_h,
            boxstyle="round,pad=0.01,rounding_size=0.01",
            linewidth=1.4, edgecolor=ACCENT, facecolor=PANEL,
        )
        ax.add_patch(box)
        ax.text(
            (x0 + x1) / 2, y_i + box_h / 2, label,
            ha="center", va="center", fontsize=13, color=TEXT, family="monospace",
        )
        if i < n - 1:
            arrow = FancyArrowPatch(
                ((x0 + x1) / 2, y_i), ((x0 + x1) / 2, y_i - gap),
                arrowstyle="-|>", mutation_scale=12, color=ACCENT, linewidth=1.2,
            )
            ax.add_patch(arrow)


def generate(
    title: str,
    kicker: str,
    out_path: pathlib.Path,
    subtitle: str = "",
    nodes: list | None = None,
    width: int = 1200,
    height: int = 630,
) -> None:
    dpi = 100
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, facecolor=BG, edgecolor="none"))
    # matplotlib's y-axis increases upward, so the accent bar sits at the top
    # of the rendered image at y=[0.95, 1.0], not y=[0, 0.05].
    ax.add_patch(mpatches.Rectangle((0, 0.95), 1, 0.05, facecolor=ACCENT, edgecolor="none"))
    # Soft corner accent — restrained, not the generic gradient-bubble look.
    ax.add_patch(mpatches.Circle((1.02, -0.05), 0.32, facecolor=ACCENT, alpha=0.08, edgecolor="none"))
    ax.add_patch(mpatches.Circle((1.0, 1.05), 0.2, facecolor=ACCENT, alpha=0.06, edgecolor="none"))

    for i, x in enumerate([0.08, 0.135, 0.19]):
        ax.add_patch(mpatches.Circle((x, 0.88), 0.011, facecolor=ACCENT, alpha=0.6 - i * 0.15))
    ax.text(0.07, 0.76, kicker.upper(), fontsize=13, color=ACCENT, weight="bold", family="monospace")

    text_width = 30 if nodes else 40
    wrapped = textwrap.fill(title, width=text_width)
    ax.text(0.07, 0.62, wrapped, fontsize=28, color=TEXT, weight="bold", va="top", family="sans-serif")

    if subtitle:
        ax.text(0.07, 0.22, textwrap.fill(subtitle, width=text_width + 6),
                 fontsize=15, color=MUTED, va="top", family="sans-serif")

    _draw_node_glyph(ax, nodes or [])

    ax.text(0.07, 0.06, "EngineeringCoders — AEP", fontsize=11, color=MUTED, family="monospace")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a code-rendered hero image (no external API).")
    parser.add_argument("--title", required=True)
    parser.add_argument("--kicker", default="engineering deep dive")
    parser.add_argument("--subtitle", default="", help="Optional one-line subtitle under the title.")
    parser.add_argument(
        "--nodes", nargs="*", default=None,
        help="Short labels for a topic-specific vertical box chain, e.g. --nodes Agent Model 'MCP server'. "
             "Omit for a plain type-only hero; always prefer passing real nodes from the article's own "
             "architecture over shipping the bare default.",
    )
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    generate(args.title, args.kicker, args.out, subtitle=args.subtitle, nodes=args.nodes)
    print(f"hero image written: {args.out}")


if __name__ == "__main__":
    main()
