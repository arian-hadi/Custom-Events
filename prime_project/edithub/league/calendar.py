"""Authoritative half-open UTC competition periods."""
from datetime import datetime, timedelta, timezone


UTC = timezone.utc


def utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware timestamp is required.")
    return value.astimezone(UTC)


def monday_for(value):
    value = utc(value)
    return value.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=value.weekday())


def next_week_start(value):
    return monday_for(value) + timedelta(days=7)


def week_cutoff(start):
    start = utc(start)
    if start != monday_for(start):
        raise ValueError("A competition starts Monday at 00:00 UTC.")
    return start + timedelta(days=5)


def friday_date(start):
    return (week_cutoff(start) - timedelta(days=1)).date()


def month_end(year, month):
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=UTC)
    return datetime(year, month + 1, 1, tzinfo=UTC)
