#!/usr/bin/env python3
"""Regenerates the stats-updated README marker with a small grey 'last updated' badge.

Stdlib only, deliberately -- no new dependencies for a personal profile README.
"""
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

README_PATH = Path(__file__).resolve().parents[2] / "README.md"


def badge_url(label: str, message: str, color: str) -> str:
    """shields.io escapes literal '-' as '--' and spaces as '_' in badge path segments."""
    def escape(s: str) -> str:
        return s.replace("-", "--").replace(" ", "_")

    return f"https://img.shields.io/badge/{quote(escape(label))}-{quote(escape(message))}-{color}?style=flat-square"


def recolor_badge(content: str, label_encoded: str, color: str) -> str:
    """The waka-readme-stats action hardcodes its Code Time / AI Code Time badges to
    -blue?style=..., with no color option. Since it overwrites those markers on every
    run, recolor them here, after it runs, so the change actually sticks."""
    return re.sub(
        rf"(badge/{re.escape(label_encoded)}-.+?)-blue(\?)",
        rf"\1-{color}\2",
        content,
    )


def replace_section(content: str, section: str, new_body: str) -> str:
    pattern = re.compile(
        rf"( *)(<!--START_SECTION:{section}-->\n)(.*?)\n( *<!--END_SECTION:{section}-->)",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise ValueError(f"Markers for section '{section}' not found in README.md")

    def substitute(m: re.Match) -> str:
        indent = m.group(1)
        return f"{indent}{m.group(2)}{indent}{new_body}\n{m.group(4)}"

    return pattern.sub(substitute, content)


def main() -> None:
    now = datetime.now(timezone.utc)
    badge = f"![last updated]({badge_url('last updated', now.strftime('%Y/%m/%d %H:%M UTC'), 'lightgrey')})"

    content = README_PATH.read_text()
    content = recolor_badge(content, "Code%20Time", "0d9488")  # teal
    content = recolor_badge(content, "AI%20Code%20Time", "8b5cf6")  # purple
    content = replace_section(content, "stats-updated", badge)
    README_PATH.write_text(content)


if __name__ == "__main__":
    main()
