"""Data profiling for the dashboard planner.

Turns a DataFrame into a compact, JSON-safe description the planner can read:
column kinds, cardinality, missing rates, numeric ranges and the date span.
Only this profile (plus a few sample rows) is ever sent to the model.
"""
from __future__ import annotations

import math
import re

import pandas as pd

SAMPLE_ROWS = 3
MAX_CATEGORICAL_CARDINALITY = 50
MAX_MISSING_PCT = 50.0

_ID_PATTERN = re.compile(r"(^id$|_id$|id$|^index$|^uuid$|_no$|_code$)", re.IGNORECASE)
_DATE_HINTS = ("date", "time", "month", "year", "day", "week")


def pretty_label(name: str) -> str:
    """`unit_price` -> `Unit Price`."""
    text = re.sub(r"[_\-]+", " ", str(name)).strip()
    return " ".join(word.capitalize() if word.islower() else word for word in text.split())


def _json_number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 4)


def _name_is_id(name: str) -> bool:
    return bool(_ID_PATTERN.search(str(name)))


def looks_like_date(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return False
    name = str(series.name).lower()
    if not any(hint in name for hint in _DATE_HINTS):
        return False
    sample = series.dropna().head(20)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce")
    return bool(parsed.notna().mean() >= 0.8)


def column_kind(df: pd.DataFrame, col: str) -> str:
    series = df[col]
    if looks_like_date(series):
        return "date"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if series.nunique(dropna=True) <= MAX_CATEGORICAL_CARDINALITY:
        return "categorical"
    return "text"


def profile_dataframe(df: pd.DataFrame) -> dict:
    """Return a JSON-safe profile of ``df``."""
    rows = len(df)
    columns: list[dict] = []
    date_range: dict | None = None

    for col in df.columns:
        series = df[col]
        kind = column_kind(df, col)
        nunique = int(series.nunique(dropna=True))
        missing_pct = round(float(series.isna().mean()) * 100, 1) if rows else 0.0

        info: dict = {
            "name": str(col),
            "kind": kind,
            "dtype": str(series.dtype),
            "missing_pct": missing_pct,
            "nunique": nunique,
            # Uniqueness only signals an ID for text-like columns: a numeric
            # measure can legitimately be unique per row (e.g. revenue).
            "is_id": bool(
                _name_is_id(col)
                or (kind in ("categorical", "text") and rows > 20 and nunique == rows)
            ),
            "usable": missing_pct <= MAX_MISSING_PCT,
        }

        if kind == "numeric":
            info["min"] = _json_number(series.min())
            info["max"] = _json_number(series.max())
            info["mean"] = _json_number(series.mean())

        if kind in ("categorical", "boolean"):
            info["top_values"] = [str(v) for v in series.dropna().value_counts().head(5).index]

        if kind == "date":
            parsed = pd.to_datetime(series, errors="coerce")
            if parsed.notna().any():
                info["min"] = str(parsed.min().date())
                info["max"] = str(parsed.max().date())
                if date_range is None:
                    date_range = {
                        "column": str(col),
                        "min": info["min"],
                        "max": info["max"],
                    }

        columns.append(info)

    sample_rows = [
        {str(key): str(value) for key, value in row.items()}
        for row in df.head(SAMPLE_ROWS).to_dict(orient="records")
    ]

    return {
        "rows": rows,
        "column_count": len(df.columns),
        "date_range": date_range,
        "columns": columns,
        "sample_rows": sample_rows,
    }


def column_map(profile: dict) -> dict[str, dict]:
    return {col["name"]: col for col in profile["columns"]}


def usable_columns(profile: dict, *kinds: str) -> list[str]:
    wanted = set(kinds) if kinds else None
    return [
        col["name"]
        for col in profile["columns"]
        if col["usable"] and not col["is_id"] and (wanted is None or col["kind"] in wanted)
    ]


def describe_profile(profile: dict) -> str:
    """One-sentence summary used for subtitles and fallback specs."""
    rows = profile["rows"]
    parts = [f"{rows:,} rows", f"{profile['column_count']} columns"]
    span = profile.get("date_range")
    if span:
        parts.append(f"{span['min']} to {span['max']}")
    return " · ".join(parts)
