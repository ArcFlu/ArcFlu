#!/usr/bin/env python3
"""Generates .github/assets/wordcloud.png from commit messages + PR titles.

MANUAL / LOCAL-ONLY -- not run by any GitHub Action.

The full-scope word cloud pulls from personal AND Squarespace repos, which
requires the operator's own authenticated `gh` CLI session (broader access
than the ArcFlu/ArcFlu repo's own GH_TOKEN secret has, and should have).
Run this locally whenever you want to refresh the image, then commit the
result.

Layout: a custom radial/starburst placement, not the `wordcloud` package's
built-in layout -- that library is a greedy nearest-fit packer with no
radial/density-falloff option, so it can only produce a uniformly packed
blob, never a "big word center, shrinking outward" look. This places the
top word dead-center, then walks subsequent words along a golden-angle
spiral with radius increasing by rank (nudged further outward, never
inward, on collision) and font size shrinking with frequency.

Setup (one-time):
    python3 -m venv /tmp/wordcloud-venv
    /tmp/wordcloud-venv/bin/pip install Pillow numpy

Usage:
    /tmp/wordcloud-venv/bin/python3 .github/scripts/generate_wordcloud.py
"""
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / ".github" / "assets" / "wordcloud.png"

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "from",
    "this", "that", "is", "are", "was", "were", "be", "been", "it", "its", "as",
    "at", "by", "not", "no", "if", "when", "into", "up", "down", "out", "so",
    "do", "does", "did", "use", "using", "used", "add", "added", "adding",
    "fix", "fixed", "fixing", "update", "updated", "updating", "remove",
    "removed", "removing", "change", "changed", "changing", "new", "some",
    "we", "i", "my", "our", "you", "your", "also", "now", "can", "should",
    "would", "will", "pr", "merge", "pull", "request", "branch", "master", "main",
}

PALETTE = ["#C15F3C", "#8C86AA", "#D9B88F", "#7EBC89", "#247BA0"]  # C1DBB3 (sage) swapped for a brown-cream -- too low-contrast against the green background
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))  # ~137.5 degrees

CANVAS = 1800
CENTER = CANVAS // 2
MAX_FONT = 220
MIN_FONT = 16
MAX_WORDS = 90
RADIUS_STEP = 10  # base px per rank, before collision nudging
COLLISION_PADDING = 2  # tight, but >1 so words never fully merge into each other
CROP_PADDING = 20


def gather_pr_titles() -> list[str]:
    result = subprocess.run(
        ["gh", "search", "prs", "--author=@me", "--limit", "1000", "--json", "title"],
        capture_output=True, text=True, check=True,
    )
    return [pr["title"] for pr in json.loads(result.stdout)]


def gather_commit_messages(repo_dirs: list[Path]) -> list[str]:
    messages = []
    for repo_dir in repo_dirs:
        if not (repo_dir / ".git").exists():
            continue
        result = subprocess.run(
            ["git", "log", "--all", "--author=ArcFlu\\|Aldrich Agabin", "--format=%s"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        messages.extend(result.stdout.splitlines())
    return messages


def clean_and_count(texts: list[str]) -> Counter:
    text = "\n".join(texts)
    text = re.sub(r"\[?\(?[A-Z]{2,10}-\d+\)?\]?", " ", text)
    text = re.sub(r"Merge (pull request|branch).*", " ", text)
    text = re.sub(r"#\d+", " ", text)
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower())
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    return Counter(words)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def word_font_size(freq: int, max_freq: int, min_freq: int) -> int:
    if max_freq == min_freq:
        return MAX_FONT
    scale = math.sqrt((freq - min_freq) / (max_freq - min_freq))
    return int(MIN_FONT + scale * (MAX_FONT - MIN_FONT))


def render_word_mask(word: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    tmp_draw = ImageDraw.Draw(Image.new("L", (1, 1), 0))
    bbox = tmp_draw.textbbox((0, 0), word, font=font)
    w, h = bbox[2] - bbox[0] + 4, bbox[3] - bbox[1] + 4
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((2 - bbox[0], 2 - bbox[1]), word, font=font, fill=255)
    return mask


def fits(occupancy: np.ndarray, mask_arr: np.ndarray, x: int, y: int) -> bool:
    h, w = mask_arr.shape
    if x < 0 or y < 0 or x + w > occupancy.shape[1] or y + h > occupancy.shape[0]:
        return False
    return not np.any(occupancy[y:y + h, x:x + w] & (mask_arr > 0))


def place_word(occupancy: np.ndarray, mask: Image.Image, angle: float, base_radius: float) -> tuple[int, int] | None:
    """Walk radius outward from base_radius until the word clears -- never inward,
    so rank still (roughly) correlates with distance from center."""
    mask_arr = np.array(mask) > 10
    h, w = mask_arr.shape
    radius = base_radius
    for _ in range(400):
        cx = CENTER + radius * math.cos(angle)
        cy = CENTER + radius * math.sin(angle)
        x, y = int(cx - w / 2), int(cy - h / 2)
        padded = np.pad(mask_arr, COLLISION_PADDING, mode="constant")
        px, py = x - COLLISION_PADDING, y - COLLISION_PADDING
        if fits(occupancy, padded, px, py):
            return px, py
        radius += 3
    return None


OUTLINE_COLOR = "#1A1A2E"
OUTLINE_WIDTH = 5


def crop_to_circle(img: Image.Image, content_radius: float, background_color: str, padding: int = CROP_PADDING) -> Image.Image:
    """Clip the image itself to a circle -- transparent outside, not just a
    square canvas with a circle drawn on top of it -- sized to just past the
    farthest-placed word, with an outline at the boundary."""
    circle_radius = int(content_radius + padding)
    margin = OUTLINE_WIDTH + 4
    side = 2 * circle_radius + 2 * margin
    left = CENTER - side // 2
    top = CENTER - side // 2

    bg_layer = Image.new("RGB", (side, side), background_color)
    src_left, src_top = max(0, left), max(0, top)
    src_right, src_bottom = min(img.width, left + side), min(img.height, top + side)
    if src_right > src_left and src_bottom > src_top:
        region = img.crop((src_left, src_top, src_right, src_bottom))
        bg_layer.paste(region, (src_left - left, src_top - top))

    mid = side // 2
    bounds = (mid - circle_radius, mid - circle_radius, mid + circle_radius, mid + circle_radius)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse(bounds, fill=255)

    result = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    result.paste(bg_layer, (0, 0), mask)
    ImageDraw.Draw(result).ellipse(bounds, outline=OUTLINE_COLOR, width=OUTLINE_WIDTH)
    return result


def generate_one(counts: Counter, background_color: str, text_colors: list[str]) -> Image.Image:
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:MAX_WORDS]
    max_freq, min_freq = ranked[0][1], ranked[-1][1]

    canvas_img = Image.new("RGB", (CANVAS, CANVAS), background_color)
    occupancy = np.zeros((CANVAS, CANVAS), dtype=bool)

    placed = 0
    max_content_radius = 0.0
    for rank, (word, freq) in enumerate(ranked):
        font = load_font(word_font_size(freq, max_freq, min_freq))
        mask = render_word_mask(word, font)
        angle = rank * GOLDEN_ANGLE
        base_radius = 0 if rank == 0 else RADIUS_STEP * math.sqrt(rank) * 2
        pos = place_word(occupancy, mask, angle, base_radius)
        if pos is None:
            continue
        x, y = pos
        color = text_colors[rank % len(text_colors)]
        mask_arr = np.array(mask)
        h, w = mask_arr.shape
        colored = Image.new("RGBA", (w, h), color)
        canvas_img.paste(colored, (x + COLLISION_PADDING, y + COLLISION_PADDING), Image.fromarray(mask_arr))
        padded_mask = np.pad(mask_arr > 10, COLLISION_PADDING, mode="constant")
        ph, pw = padded_mask.shape
        occupancy[y:y + ph, x:x + pw] |= padded_mask
        placed += 1

        for cx, cy in ((x, y), (x + pw, y), (x, y + ph), (x + pw, y + ph)):
            max_content_radius = max(max_content_radius, math.hypot(cx - CENTER, cy - CENTER))

    print(f"  placed {placed}/{len(ranked)} words")
    return crop_to_circle(canvas_img, max_content_radius, background_color)


BACKGROUND_COLOR = "#7EBC89"  # chosen after comparing all 5 palette colors as backgrounds


def main() -> None:
    repo_dirs = [p for p in REPO_ROOT.parent.iterdir() if p.is_dir()]
    counts = clean_and_count(gather_pr_titles() + gather_commit_messages(repo_dirs))
    text_colors = [c for c in PALETTE if c != BACKGROUND_COLOR]

    img = generate_one(counts, BACKGROUND_COLOR, text_colors)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
