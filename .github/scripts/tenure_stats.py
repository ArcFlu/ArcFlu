#!/usr/bin/env python3
"""Regenerates the tenure-squarespace and tenure-coding README sections.

Stdlib only, deliberately -- no new dependencies for a personal profile README.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

README_PATH = Path(__file__).resolve().parents[2] / "README.md"

SQSP_START = datetime(2024, 5, 15, tzinfo=timezone.utc)
UCF_START = datetime(2020, 8, 24, tzinfo=timezone.utc)

YEAR_SECONDS = 365.25 * 24 * 3600
MONTH_SECONDS = 30.44 * 24 * 3600
DAY_SECONDS = 24 * 3600
HOUR_SECONDS = 3600.0
MINUTE_SECONDS = 60.0


def scaled(n: float) -> str:
    """Abbreviate large numbers with K/M/B suffixes for readability."""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= threshold:
            return f"{n / threshold:,.1f}{suffix}"
    return f"{n:,.1f}"


def format_units(total_seconds: float) -> str:
    """Each unit expresses the *entire* elapsed duration, not a decomposed breakdown.
    Minutes/seconds are scale-abbreviated (e.g. 72.5M) -- raw comma-separated values
    in the millions are hard to parse at a glance and undercut the joke."""
    return (
        f"{total_seconds / YEAR_SECONDS:,.1f} years / "
        f"{total_seconds / MONTH_SECONDS:,.1f} months / "
        f"{total_seconds / DAY_SECONDS:,.1f} days / "
        f"{total_seconds / HOUR_SECONDS:,.1f} hours / "
        f"{scaled(total_seconds / MINUTE_SECONDS)} minutes / "
        f"{scaled(total_seconds)} seconds"
    )


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    """weekday: Monday=0 ... Sunday=6. n is the 1-indexed occurrence in the month."""
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def last_weekday_of_month(year: int, month: int, weekday: int) -> datetime:
    next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    d = next_month - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def observed(d: datetime) -> datetime:
    """Federal observance rule: Saturday holidays move to Friday, Sunday to Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def squarespace_holidays(year: int) -> set:
    """US federal holidays (observed), minus Columbus Day & Veterans Day, plus the
    Friday after Thanksgiving (Native American Heritage Day). Mirrors the holiday
    rule in sqsp/analytics-composer's dags/finance_systems/nspb/calendar.py."""
    thanksgiving = nth_weekday_of_month(year, 11, 3, 4)
    return {
        observed(datetime(year, 1, 1, tzinfo=timezone.utc)),
        observed(nth_weekday_of_month(year, 1, 0, 3)),
        observed(nth_weekday_of_month(year, 2, 0, 3)),
        observed(last_weekday_of_month(year, 5, 0)),
        observed(datetime(year, 6, 19, tzinfo=timezone.utc)),
        observed(datetime(year, 7, 4, tzinfo=timezone.utc)),
        observed(nth_weekday_of_month(year, 9, 0, 1)),
        observed(thanksgiving),
        observed(thanksgiving + timedelta(days=1)),
        observed(datetime(year, 12, 25, tzinfo=timezone.utc)),
    }


def business_hours_since(start: datetime, end: datetime) -> float:
    """8 hours per weekday, excluding Squarespace-observed holidays."""
    holiday_cache: dict[int, set] = {}
    day = start.date()
    end_date = end.date()
    work_hours = 0.0
    while day <= end_date:
        if day.year not in holiday_cache:
            holiday_cache[day.year] = {h.date() for h in squarespace_holidays(day.year)}
        if day.weekday() < 5 and day not in holiday_cache[day.year]:
            work_hours += 8
        day += timedelta(days=1)
    return work_hours


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
    now = datetime.now(timezone.utc)
    last_updated = now.strftime("%Y/%m/%d %H:%M UTC")

    sqsp_elapsed_seconds = (now - SQSP_START).total_seconds()
    work_hours = business_hours_since(SQSP_START, now)
    coding_elapsed_seconds = (now - UCF_START).total_seconds()

    sqsp_body = (
        f"<sub><em>🎉 That's {format_units(sqsp_elapsed_seconds)} of being a Squarespace SWE "
        f"-- or, at a very scientific 8 hours/workday (weekdays minus Squarespace holidays), "
        f"{format_units(work_hours * HOUR_SECONDS)} of actual keyboard-touching. "
        f"(last updated {last_updated})</em></sub>"
    )
    coding_body = (
        f"<sub><em>👨‍💻 That's {format_units(coding_elapsed_seconds)} of coding (allegedly). "
        f"(last updated {last_updated})</em></sub>"
    )

    content = README_PATH.read_text()
    content = replace_section(content, "tenure-squarespace", sqsp_body)
    content = replace_section(content, "tenure-coding", coding_body)
    README_PATH.write_text(content)


if __name__ == "__main__":
    main()
