"""Pure, local departure normalization; no Home Assistant dependencies."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from math import ceil, isfinite
from typing import Any

from .const import DEFAULT_HORIZON, DEFAULT_LIMIT

_LINE_SPACES = re.compile(r"\s+")
_MAIN_STATION = re.compile(r"\bHauptbahnhof\b", re.IGNORECASE)
_DATETIME_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}")

MODE_FAMILIES = {
    "bus": "bus",
    "tram": "tram",
    "streetcar": "tram",
    "subway": "subway",
    "metro": "subway",
    "suburban": "train",
    "suburban_rail": "train",
    "s-bahn": "train",
    "train": "train",
    "rail": "train",
    "regional": "train",
    "regional_express": "train",
    "national": "train",
    "national_express": "train",
    "ferry": "ferry",
}
ICONS = {
    name: "mdi:" + ("subway-variant" if family == "subway" else family)
    for name, family in MODE_FAMILIES.items()
}


@dataclass
class Board:
    """One displayed snapshot, independent of earlier countdown values."""

    departures: list[dict[str, Any]]
    duplicates_removed: int = 0
    invalid_rows: int = 0


@dataclass
class PreparedBoard:
    """Normalized, sorted schedule reused until source data changes."""

    schedule: list[tuple[datetime, dict[str, Any]]]
    duplicates_removed: int = 0
    invalid_rows: int = 0

    def at(self, now: datetime, *, limit: int = DEFAULT_LIMIT, horizon: int = DEFAULT_HORIZON) -> Board:
        """Project the visible time window; copy only displayed row dictionaries."""
        end = now + timedelta(minutes=horizon)
        departures: list[dict[str, Any]] = []
        for actual, payload in self.schedule:
            if actual < now:
                continue
            if actual > end or len(departures) >= limit:
                break
            departures.append(
                {
                    **payload,
                    "countdown_minutes": max(0, ceil((actual - now).total_seconds() / 60)),
                }
            )
        return Board(departures, self.duplicates_removed, self.invalid_rows)


def text(value: Any) -> str:
    """Accept finite scalar text, rejecting structured or oversized values."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    if isinstance(value, float) and not isfinite(value):
        return ""
    try:
        return str(value).strip()
    except (ValueError, OverflowError):
        return ""


def number(value: Any) -> float | None:
    """Read a finite number without accepting booleans as 0/1."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def timestamp(value: Any, local_tz: tzinfo) -> datetime | None:
    """Require a date and clock time; interpret naive values in the HA timezone."""
    if not isinstance(value, datetime) and (not isinstance(value, str) or not _DATETIME_PREFIX.match(value)):
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=local_tz)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def short_destination(value: str) -> str:
    """Apply a generic display abbreviation, independent of the station."""
    return _MAIN_STATION.sub("Hbf", value)


def _normalize(
    raw: Any, entity: str, group: str, local_tz: tzinfo, delay_unit: str
) -> tuple[datetime, dict[str, Any]] | None:
    """Normalize one source row without depending on the current clock."""
    if not isinstance(raw, Mapping):
        return None
    line, destination = text(raw.get("line")), text(raw.get("destination"))
    planned = timestamp(raw.get("planned_time"), local_tz)
    actual_raw = raw.get("departure_time")
    actual = timestamp(actual_raw, local_tz)
    delay = number(raw.get("delay"))
    if delay is not None and delay_unit == "seconds":
        delay /= 60
    if actual is None and actual_raw not in (None, ""):
        return None
    if actual is None and planned is not None:
        try:
            actual = planned + timedelta(minutes=delay or 0)
        except OverflowError:
            return None
    if not line or not destination or actual is None:
        return None
    if delay is None and planned is not None and actual_raw not in (None, ""):
        delay = (actual - planned).total_seconds() / 60
    if planned is None and delay is not None:
        try:
            planned = actual - timedelta(minutes=delay)
        except OverflowError:
            pass
    mode = text(raw.get("transportation_type")) or "unknown"
    agency = text(raw.get("agency")) or None
    return actual, {
        "line": line,
        "destination": destination,
        "destination_short": short_destination(destination),
        "departure_time": actual.isoformat(),
        "planned_time": planned.isoformat() if planned else None,
        "delay": delay,
        "platform": text(raw.get("platform")) or None,
        "transportation_type": mode,
        "icon": ICONS.get(mode.casefold().replace(" ", "_"), "mdi:public-transport"),
        "minutes_until_departure": number(raw.get("minutes_until_departure")),
        "agency": agency,
        "agencies": [agency] if agency else [],
        "source_entities": [entity],
        "stop_group": group,
        "cancelled": raw.get("cancelled") is True,
    }


def prepare_departures(
    sources: Mapping[str, Any],
    groups: Mapping[str, str],
    local_tz: tzinfo,
    *,
    delay_unit: str = "minutes",
    delay_units: Mapping[str, str] | None = None,
) -> PreparedBoard:
    """Deduplicate by stop, mode family, line, target and stable planned time."""
    board = PreparedBoard([])
    unique: dict[tuple[str, ...], tuple[datetime, dict[str, Any]]] = {}
    for entity, rows in sources.items():
        group = groups.get(entity) or entity
        group_key = group.casefold()
        unit = (delay_units or {}).get(entity, delay_unit)
        if not isinstance(rows, (list, tuple)):
            continue
        for raw in rows:
            normalized = _normalize(raw, entity, group, local_tz, unit)
            if normalized is None:
                board.invalid_rows += 1
                continue
            actual, dep = normalized
            mode = dep["transportation_type"].casefold().replace(" ", "_")
            # Identity uses stable families, independent of icon presentation.
            family = MODE_FAMILIES.get(mode, mode)
            key = (
                group_key,
                family,
                _LINE_SPACES.sub("", dep["line"]).casefold(),
                " ".join(dep["destination_short"].casefold().split()),
                "planned" if dep["planned_time"] else "actual",
                dep["planned_time"] or dep["departure_time"],
            )
            if key in unique:
                winner = unique[key][1]
                for field in ("agencies", "source_entities"):
                    for value in dep[field]:
                        if value not in winner[field]:
                            winner[field].append(value)
                board.duplicates_removed += 1
            else:
                unique[key] = (actual, dep)
    board.schedule = sorted(
        unique.values(), key=lambda item: (item[0], item[1]["line"], item[1]["destination"])
    )
    return board


def build_departures(
    sources: Mapping[str, Any],
    groups: Mapping[str, str],
    now: datetime,
    local_tz: tzinfo,
    *,
    delay_unit: str = "minutes",
    delay_units: Mapping[str, str] | None = None,
    limit: int = DEFAULT_LIMIT,
    horizon: int = DEFAULT_HORIZON,
) -> Board:
    """Convenience API for callers that need a single complete snapshot."""
    return prepare_departures(
        sources,
        groups,
        local_tz,
        delay_unit=delay_unit,
        delay_units=delay_units,
    ).at(
        now,
        limit=limit,
        horizon=horizon,
    )
