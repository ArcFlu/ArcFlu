#!/usr/bin/env python3
"""Generates .github/assets/wordcloud.png from commit messages + PR titles.

MANUAL / LOCAL-ONLY -- not run by any GitHub Action.

The full-scope word cloud pulls from personal AND Squarespace repos, which
requires the operator's own authenticated `gh` CLI session (broader access
than the ArcFlu/ArcFlu repo's own GH_TOKEN secret has, and should have).
Run this locally whenever you want to refresh the image, then commit the
result.

Setup (one-time):
    python3 -m venv /tmp/wordcloud-venv
    /tmp/wordcloud-venv/bin/pip install wordcloud matplotlib Pillow numpy

Usage:
    /tmp/wordcloud-venv/bin/python3 .github/scripts/generate_wordcloud.py
"""
import random
import re
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from wordcloud import WordCloud

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

BRAND_COLORS = ["#D97757", "#478CBF", "#0E75B6", "#F4A261"]


def gather_pr_titles() -> list[str]:
    result = subprocess.run(
        ["gh", "search", "prs", "--author=@me", "--limit", "1000", "--json", "title"],
        capture_output=True, text=True, check=True,
    )
    import json
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


def circle_mask(size: int = 1000) -> np.ndarray:
    mask_img = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(mask_img)
    draw.ellipse((20, 20, size - 20, size - 20), fill=0)
    return np.array(mask_img)


def brand_color(word, font_size, position, orientation, random_state=None, **kwargs):
    return random.choice(BRAND_COLORS)


def main() -> None:
    repo_dirs = [p for p in REPO_ROOT.parent.iterdir() if p.is_dir()]
    counts = clean_and_count(gather_pr_titles() + gather_commit_messages(repo_dirs))

    wc = WordCloud(
        width=1000, height=1000, background_color="white",
        mask=circle_mask(), color_func=brand_color, max_words=150,
        prefer_horizontal=0.9, contour_width=2, contour_color="#1A1A2E",
    )
    wc.generate_from_frequencies(counts)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wc.to_file(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
