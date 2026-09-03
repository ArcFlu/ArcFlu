#!/usr/bin/env python3
"""Regenerates the all-time contributions README section via GitHub's GraphQL API.

Stdlib only, deliberately -- no new dependencies for a personal profile README.

GitHub's `contributionsCollection` query only accepts windows of at most one year,
and there's no all-time total exposed directly, so this walks year-by-year from
account creation to now and sums totalCommitContributions, totalPullRequestContributions,
totalPullRequestReviewContributions, and totalIssueContributions -- the four inputs
that make up the profile contribution graph's total.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

README_PATH = Path(__file__).resolve().parents[2] / "README.md"
GITHUB_LOGIN = "arcflu"
GRAPHQL_URL = "https://api.github.com/graphql"

CREATED_AT_QUERY = """
query($login: String!) {
  user(login: $login) { createdAt }
}
"""

CONTRIBUTIONS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
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


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def year_windows(start: datetime, end: datetime):
    cursor = start
    while cursor < end:
        window_end = min(datetime(cursor.year + 1, cursor.month, cursor.day, tzinfo=timezone.utc), end)
        yield cursor, window_end
        cursor = window_end


def fetch_all_time_totals(token: str) -> dict:
    created_at = datetime.strptime(
        graphql(token, CREATED_AT_QUERY, {"login": GITHUB_LOGIN})["user"]["createdAt"],
        "%Y-%m-%dT%H:%M:%SZ",
    ).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    totals = {
        "totalCommitContributions": 0,
        "totalPullRequestContributions": 0,
        "totalPullRequestReviewContributions": 0,
        "totalIssueContributions": 0,
    }
    for window_start, window_end in year_windows(created_at, now):
        data = graphql(
            token,
            CONTRIBUTIONS_QUERY,
            {"login": GITHUB_LOGIN, "from": iso(window_start), "to": iso(window_end)},
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
        ("Commits", totals["totalCommitContributions"]),
        ("PRs", totals["totalPullRequestContributions"]),
        ("PRs Reviewed", totals["totalPullRequestReviewContributions"]),
        ("Issues", totals["totalIssueContributions"]),
    ]
    badges = "\n".join(f"![{label}]({badge_url(label, f'{count:,}', 'blue')})" for label, count in labeled_counts)

    content = README_PATH.read_text()
    content = replace_section(content, "contributions", badges)
    README_PATH.write_text(content)


if __name__ == "__main__":
    main()
