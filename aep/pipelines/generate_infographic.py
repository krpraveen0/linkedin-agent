#!/usr/bin/env python3
"""Generate a concept-infographic without any external API call.

Companion to generate_hero_image.py, for the case aep/prompts/writer.md's
"Concept density" rule targets: 3+ parallel, bold-labeled items (a features
list, a set of trade-offs, a comparison of options) that would otherwise
ship as another prose bullet list. Render them as labeled cards instead —
matplotlib only, per aep/policies/no-external-llm-policy.md, so this stays
a local, code-rendered asset with no network call or image-gen API.

Usage:
    python3 generate_infographic.py \
        --title "MCP core primitives" \
        --item "Resources:Static or queryable data the server exposes" \
        --item "Tools:Executable functions the model can invoke" \
        --item "Prompts:Reusable templates for common interactions" \
        --out assets/mcp-primitives-infographic.png
"""
import argparse
import pathlib
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
ACCENT = "#2f81f7"
TEXT = "#f0f6fc"
MUTED = "#8b949e"

MAX_COLUMNS = 4


def _parse_item(raw: str) -> tuple:
    if ":" not in raw:
        raise argparse.ArgumentTypeError(
            f"--item must be 'Label:Description', got: {raw!r}"
        )
    label, _, description = raw.partition(":")
    return label.strip(), description.strip()


def generate(
    title: str,
    items: list,
    out_path: pathlib.Path,
    kicker: str = "",
    width: int = 1200,
) -> None:
    n = len(items)
    if n < 2:
        raise ValueError("an infographic needs at least 2 items — use prose for a single point")

    columns = min(n, MAX_COLUMNS)
    rows = -(-n // columns)  # ceil division
    card_h = 0.30
    height = int(width * (0.22 + rows * 0.30))

    dpi = 100
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, facecolor=BG, edgecolor="none"))

    if kicker:
        ax.text(0.04, 0.965, kicker.upper(), fontsize=11, color=ACCENT,
                 weight="bold", family="monospace", va="top")
    ax.text(0.04, 0.92, title, fontsize=20, color=TEXT, weight="bold",
            family="sans-serif", va="top")

    grid_top = 0.80
    col_w = 0.94 / columns
    margin = 0.03

    for i, (label, description) in enumerate(items):
        row = i // columns
        col = i % columns
        x0 = margin + col * col_w
        y0 = grid_top - (row + 1) * (card_h + 0.04)

        card = mpatches.FancyBboxPatch(
            (x0, y0), col_w - 0.03, card_h,
            boxstyle="round,pad=0.006,rounding_size=0.012",
            linewidth=1.2, edgecolor=BORDER, facecolor=PANEL,
        )
        ax.add_patch(card)

        badge = mpatches.Circle((x0 + 0.04, y0 + card_h - 0.055), 0.022, facecolor=ACCENT, edgecolor="none")
        ax.add_patch(badge)
        ax.text(x0 + 0.04, y0 + card_h - 0.055, str(i + 1), ha="center", va="center",
                fontsize=11, color=BG, weight="bold", family="monospace")

        ax.text(x0 + 0.075, y0 + card_h - 0.06, textwrap.fill(label, width=18),
                fontsize=13.5, color=TEXT, weight="bold", va="top", family="sans-serif")

        wrapped_desc = textwrap.fill(description, width=26)
        ax.text(x0 + 0.02, y0 + card_h - 0.13, wrapped_desc,
                fontsize=10.5, color=MUTED, va="top", family="sans-serif")

    ax.text(0.04, 0.02, "EngineeringCoders — AEP", fontsize=9, color=MUTED, family="monospace")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a code-rendered concept-infographic (no external API).")
    parser.add_argument("--title", required=True)
    parser.add_argument("--kicker", default="")
    parser.add_argument(
        "--item", dest="items", action="append", type=_parse_item, required=True,
        help="Repeatable. Format: 'Label:Description'. Provide 2-8 items.",
    )
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    generate(args.title, args.items, args.out, kicker=args.kicker)
    print(f"infographic written: {args.out}")


if __name__ == "__main__":
    main()
