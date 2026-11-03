#!/usr/bin/env python3
"""Regenerates the all-time contributions README section via GitHub's GraphQL API.

Stdlib only, deliberately -- no new dependencies for a personal profile README.

GitHub's `contributionsCollection` query only accepts windows of at most one year,
and there's no all-time total exposed directly, so this walks year-by-year and sums
totalCommitContributions, totalPullRequestContributions, and
totalPullRequestReviewContributions.

Squarespace's private repos stopped counting toward those totals when org access
ended with the Nov 2, 2026 layoff (GitHub only reports them as anonymized restricted
contributions now), so totals through BASELINE_THROUGH are frozen in
BASELINE_TOTALS and only later contributions are fetched live.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

README_PATH = Path(__file__).resolve().parents[2] / "README.md"
GITHUB_LOGIN = "arcflu"
GRAPHQL_URL = "https://api.github.com/graphql"

# Totals through Squarespace's last day, captured by a one-off run on Nov 2, 2026 whose
# token could still see its repos, using the year windows behind the totals published before.
BASELINE_THROUGH = date(2026, 11, 2)
BASELINE_TOTALS = {
    "totalCommitContributions": 2791,
    "totalPullRequestContributions": 797,
    "totalPullRequestReviewContributions": 522,
}

CONTRIBUTIONS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
    }
  }
}
"""


def graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    if "errors" in body:
        raise RuntimeError(f"GraphQL error: {body['errors']}")
    return body["data"]


def year_windows(start: date, end: date):
    """contributionsCollection ignores the time of day and treats `from` and `to` as
    inclusive dates, so windows must not share a date."""
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=364), end)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def fetch_all_time_totals(token: str) -> dict:
    totals = dict(BASELINE_TOTALS)
    today = datetime.now(timezone.utc).date()
    for window_start, window_end in year_windows(BASELINE_THROUGH + timedelta(days=1), today):
        data = graphql(
            token,
            CONTRIBUTIONS_QUERY,
            {"login": GITHUB_LOGIN, "from": f"{window_start}T00:00:00Z", "to": f"{window_end}T23:59:59Z"},
        )["user"]["contributionsCollection"]
        for key in totals:
            totals[key] += data[key]
    return totals


def badge_url(label: str, message: str, color: str) -> str:
    """shields.io escapes literal '-' as '--' and spaces as '_' in badge path segments."""
    def escape(s: str) -> str:
        return s.replace("-", "--").replace(" ", "_")

    return f"https://img.shields.io/badge/{quote(escape(label))}-{quote(escape(message))}-{color}?style=flat"


def replace_section(content: str, section: str, new_body: str) -> str:
    pattern = re.compile(
        rf"( *)(<!--START_SECTION:{section}-->\n)(.*?)\n( *<!--END_SECTION:{section}-->)",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise ValueError(f"Markers for section '{section}' not found in README.md")

    def substitute(m: re.Match) -> str:
        indent = m.group(1)
        indented_body = "\n".join(f"{indent}{line}" if line else "" for line in new_body.split("\n"))
        return f"{indent}{m.group(2)}{indented_body}\n{m.group(4)}"

    return pattern.sub(substitute, content)


def main() -> None:
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("GH_TOKEN not set, skipping contribution stats update.", file=sys.stderr)
        return

    totals = fetch_all_time_totals(token)

    labeled_counts = [
        ("Commits", totals["totalCommitContributions"], "0e75b6"),
        ("PRs", totals["totalPullRequestContributions"], "f97316"),
        ("PRs Reviewed", totals["totalPullRequestReviewContributions"], "22c55e"),
    ]
    badges = "\n".join(f"![{label}]({badge_url(label, f'{count:,}', color)})" for label, count, color in labeled_counts)

    content = README_PATH.read_text()
    content = replace_section(content, "contributions", badges)
    README_PATH.write_text(content)


if __name__ == "__main__":
    main()
