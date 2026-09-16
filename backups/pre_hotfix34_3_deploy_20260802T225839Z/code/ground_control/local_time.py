"""Los Angeles clock helpers for Ground Control."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE_NAME = "America/Los_Angeles"
LOCAL_TIMEZONE = ZoneInfo(LOCAL_TIMEZONE_NAME)


def as_local_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(LOCAL_TIMEZONE)


def local_now() -> datetime:
    return datetime.now(LOCAL_TIMEZONE)


def local_date(value: datetime | None = None) -> date:
    return as_local_time(value).date() if value is not None else local_now().date()


def greeting_for_datetime(value: datetime) -> str:
    hour = as_local_time(value).hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def format_local_datetime(value: datetime) -> str:
    local_value = as_local_time(value)
    return (
        f"{local_value.strftime('%A, %B')} {local_value.day}, {local_value.year}"
        f" · {local_value.strftime('%-I:%M:%S %p %Z')}"
    )
