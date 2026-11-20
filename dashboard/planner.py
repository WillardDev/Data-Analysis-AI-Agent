"""Dashboard planning.

The planner asks the model for a JSON dashboard spec (never plotting code),
validates it against the data profile, and falls back to a rule-based
dashboard when the model returns something unusable.
"""
from __future__ import annotations

import json
import time

from .profile import (
    column_map,
    describe_profile,
    pretty_label,
    usable_columns,
)

ALLOWED_TYPES = (
    "line",
    "bar",
    "hbar",
    "stacked_bar",
    "pie",
    "scatter",
    "histogram",
    "box",
    "heatmap",
    "table",
)
ALLOWED_AGGS = ("sum", "mean", "count", "median")
ALLOWED_FORMATS = ("currency", "number", "percent")
MAX_CHARTS = 6
MAX_KPIS = 4
MAX_FILTERS = 3
MAX_TOP_N = 50
DEFAULT_TOP_N = 10
MAX_PIE_SLICES = 5

MONEY_HINTS = ("revenue", "sales", "amount", "total", "price", "value", "cost", "profit")

SYSTEM_PROMPT = """You are a dashboard planner for a business user who does not code.
You receive a data profile and return ONLY a JSON object describing a dashboard.
You never write Python or plotting code.

Schema:
{
  "title": "string",
  "subtitle": "one sentence describing the data and date range",
  "kpis": [{"label": "Total revenue", "column": "revenue", "agg": "sum|mean|count|median", "format": "currency|number|percent"}],
  "charts": [{"type": "line|bar|hbar|stacked_bar|pie|scatter|histogram|box|heatmap|table",
              "title": "string", "x": "column", "y": "column", "color": "column or null",
              "agg": "sum|mean|count|median", "top_n": 10,
              "insight": "one plain-English sentence supported by the data"}],
  "filters": ["up to 3 categorical or date columns"]
}

Rules:
- Use ONLY columns present in the profile. Never invent names.
- Skip ID-like columns and columns with more than 50% missing values.
- Date column + numeric measure -> line chart, aggregated by month (or week for short spans).
- Category + numeric measure -> horizontal bar, sorted, top 10 plus an "Other" bucket.
- Parts of a whole with 5 or fewer categories -> pie; more than 5 -> bar.
- Two categories + one measure -> stacked_bar or heatmap.
- Two numeric columns -> scatter, colored by a category when one exists.
- Single numeric column -> histogram; comparing groups -> box.
- Never use 3D charts, dual axes, or more than 6 charts.
- 3 to 4 KPIs. Prefer fewer, clearer visuals.
- Every insight must be checkable from the data. Do not invent numbers.
Return JSON only, with no markdown fences or commentary."""


def build_prompt(profile: dict, focus: str | None = None) -> str:
    payload = {
        "profile": profile,
        "focus": (focus or "").strip() or None,
    }
    return (
        "Build a dashboard spec from this profile.\n\n"
        + json.dumps(payload, indent=2)
        + "\n\nReturn only the JSON object."
    )


def parse_json(text: str) -> dict:
    """Parse JSON, tolerating markdown fences or leading prose."""
    if not text:
        raise ValueError("empty response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(cleaned[start : end + 1])


def _text(value, default: str, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip()[:limit]


def _is_money(column: str) -> bool:
    name = str(column).lower()
    return any(hint in name for hint in MONEY_HINTS)


TOTAL_HINTS = ("revenue", "sales", "amount", "total", "profit", "spend", "income", "cost")
RATE_HINTS = ("price", "rate", "pct", "percent", "ratio", "unit")


def _measure_rank(column: str) -> int:
    """Rank measures so totals lead: revenue > generic numeric > unit price."""
    name = str(column).lower()
    if any(hint in name for hint in TOTAL_HINTS):
        return 0
    if any(hint in name for hint in RATE_HINTS):
        return 2
    return 1


def _primary_measure(numeric: list[str]) -> str | None:
    if not numeric:
        return None
    return min(numeric, key=lambda col: (_measure_rank(col), numeric.index(col)))


def _kpi_agg_and_format(column: str) -> tuple[str, str]:
    name = str(column).lower()
    if _is_money(column):
        if any(key in name for key in ("price", "rate", "unit")):
            return "mean", "currency"
        return "sum", "currency"
    if any(key in name for key in ("pct", "percent", "rate", "ratio")):
        return "mean", "percent"
    return "sum", "number"


def fallback_kpis(profile: dict) -> list[dict]:
    numeric = usable_columns(profile, "numeric")
    ordered = sorted(numeric, key=lambda col: (_measure_rank(col), numeric.index(col)))
    kpis = []
    for column in ordered[:MAX_KPIS]:
        agg, fmt = _kpi_agg_and_format(column)
        kpis.append(
            {
                "label": pretty_label(column),
                "column": column,
                "agg": agg,
                "format": fmt,
            }
        )
    if len(kpis) < 3 and profile["columns"]:
        kpis.append(
            {
                "label": "Rows",
                "column": profile["columns"][0]["name"],
                "agg": "count",
                "format": "number",
            }
        )
    return kpis[:MAX_KPIS]


def _chart(ctype: str, title: str, x, y, color=None, agg="sum", top_n=DEFAULT_TOP_N, insight=""):
    return {
        "type": ctype,
        "title": title,
        "x": x,
        "y": y,
        "color": color,
        "agg": agg,
        "top_n": top_n,
        "insight": insight,
    }


def fallback_spec(profile: dict) -> dict:
    """Rule-based dashboard used when the model output cannot be used."""
    cols = column_map(profile)
    numeric = usable_columns(profile, "numeric")
    categorical = [
        c
        for c in usable_columns(profile, "categorical", "boolean")
        if 1 < cols[c]["nunique"] <= 50
    ]
    dates = usable_columns(profile, "date")
    date_col = dates[0] if dates else None
    primary = _primary_measure(numeric)

    charts: list[dict] = []
    if date_col and primary:
        charts.append(
            _chart("line", f"{pretty_label(primary)} over time", date_col, primary)
        )
    if categorical and primary:
        charts.append(
            _chart(
                "hbar",
                f"{pretty_label(primary)} by {pretty_label(categorical[0])}",
                categorical[0],
                primary,
                top_n=DEFAULT_TOP_N,
            )
        )
    if len(categorical) >= 2 and primary:
        charts.append(
            _chart(
                "stacked_bar",
                f"{pretty_label(primary)} by {pretty_label(categorical[0])} and {pretty_label(categorical[1])}",
                categorical[0],
                primary,
                color=categorical[1],
            )
        )
    others = [c for c in numeric if c != primary]
    secondary = min(others, key=lambda col: (_measure_rank(col), numeric.index(col))) if others else None

    if primary and secondary:
        charts.append(
            _chart(
                "scatter",
                f"{pretty_label(primary)} vs {pretty_label(secondary)}",
                secondary,
                primary,
                color=categorical[0] if categorical else None,
            )
        )
    if secondary:
        charts.append(
            _chart("histogram", f"Distribution of {pretty_label(secondary)}", secondary, None)
        )
    if categorical and primary:
        charts.append(
            _chart(
                "box",
                f"{pretty_label(primary)} by {pretty_label(categorical[0])}",
                categorical[0],
                primary,
            )
        )
    if categorical and len(charts) < MAX_CHARTS:
        last = categorical[-1]
        ctype = "pie" if cols[last]["nunique"] <= MAX_PIE_SLICES else "bar"
        charts.append(
            _chart(ctype, f"Share by {pretty_label(last)}", last, primary)
        )

    # De-duplicate identical (type, x, y) triples.
    seen, unique = set(), []
    for chart in charts:
        key = (chart["type"], chart["x"], chart["y"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(chart)

    filters = ([date_col] if date_col else []) + categorical[:2]

    return {
        "title": "Data overview",
        "subtitle": describe_profile(profile),
        "kpis": fallback_kpis(profile),
        "charts": unique[:MAX_CHARTS],
        "filters": filters[:MAX_FILTERS],
    }


def _validate_chart(chart, cols: dict) -> tuple[dict | None, str | None]:
    if not isinstance(chart, dict):
        return None, "chart is not an object"

    ctype = chart.get("type")
    if ctype not in ALLOWED_TYPES:
        return None, f"unsupported chart type {ctype!r}"

    x, y, color = chart.get("x"), chart.get("y"), chart.get("color")

    for value, label in ((x, "x"), (y, "y")):
        if value not in (None, "") and value not in cols:
            return None, f"unknown {label} column {value!r}"

    if color not in (None, "") and color not in cols:
        color = None

    def kind(column):
        return cols[column]["kind"] if column in cols else None

    def is_dimension(column):
        return kind(column) in ("categorical", "boolean", "date")

    def is_measure(column):
        return kind(column) == "numeric"

    # Models sometimes put the measure on x for horizontal bars (or swap the
    # axes for line/box). Swap back rather than dropping a usable chart.
    if ctype in ("bar", "hbar", "stacked_bar", "pie", "line", "box"):
        if x and y and is_measure(x) and is_dimension(y):
            x, y = y, x

    if ctype == "line" and not (kind(x) == "date" and kind(y) == "numeric"):
        return None, "line needs a date x and a numeric y"
    if ctype in ("bar", "hbar", "stacked_bar", "pie"):
        if not is_dimension(x) or kind(y) != "numeric":
            return None, f"{ctype} needs a category x and a numeric y"
    if ctype == "scatter" and not (kind(x) == "numeric" and kind(y) == "numeric"):
        return None, "scatter needs two numeric columns"
    if ctype == "histogram" and kind(x) != "numeric":
        return None, "histogram needs a numeric x"
    if ctype == "box" and kind(y) != "numeric":
        return None, "box needs a numeric y"
    if ctype == "heatmap" and not (
        kind(x) in ("categorical", "boolean", "date")
        and kind(y) in ("categorical", "boolean", "date")
    ):
        return None, "heatmap needs two categorical columns"
    if ctype == "table" and x in (None, "") and y in (None, ""):
        return None, "table needs at least one column"

    # Pie charts with too many slices are downgraded rather than dropped.
    if ctype == "pie" and cols[x]["nunique"] > MAX_PIE_SLICES:
        ctype = "bar"

    agg = chart.get("agg") if chart.get("agg") in ALLOWED_AGGS else "sum"
    if agg != "count" and kind(y) != "numeric":
        agg = "count"

    try:
        top_n = int(chart.get("top_n") or DEFAULT_TOP_N)
    except (TypeError, ValueError):
        top_n = DEFAULT_TOP_N
    top_n = max(1, min(MAX_TOP_N, top_n))

    default_title = (
        f"{pretty_label(y)} by {pretty_label(x)}"
        if y
        else pretty_label(x or "Overview")
    )

    return (
        {
            "type": ctype,
            "title": _text(chart.get("title"), default_title),
            "x": x or None,
            "y": y or None,
            "color": color or None,
            "agg": agg,
            "top_n": top_n,
            "insight": _text(chart.get("insight"), "", limit=240),
        },
        None,
    )


def validate_spec(spec, profile: dict) -> tuple[dict | None, list[dict]]:
    """Drop anything that references missing columns or incompatible types."""
    if not isinstance(spec, dict):
        return None, [{"item": "spec", "reason": "not a JSON object"}]

    cols = column_map(profile)
    dropped: list[dict] = []

    clean = {
        "title": _text(spec.get("title"), "Data overview"),
        "subtitle": _text(spec.get("subtitle"), describe_profile(profile)),
        "kpis": [],
        "charts": [],
        "filters": [],
    }

    for kpi in spec.get("kpis") or []:
        if len(clean["kpis"]) >= MAX_KPIS:
            break
        if not isinstance(kpi, dict):
            dropped.append({"item": "kpi", "reason": "not an object"})
            continue
        column = kpi.get("column")
        if column not in cols:
            dropped.append({"item": kpi.get("label") or column, "reason": f"unknown column {column!r}"})
            continue
        agg = kpi.get("agg") if kpi.get("agg") in ALLOWED_AGGS else "sum"
        if agg != "count" and cols[column]["kind"] != "numeric":
            dropped.append({"item": kpi.get("label") or column, "reason": "aggregation needs a numeric column"})
            continue
        fmt = kpi.get("format") if kpi.get("format") in ALLOWED_FORMATS else "number"
        clean["kpis"].append(
            {
                "label": _text(kpi.get("label"), pretty_label(column)),
                "column": column,
                "agg": agg,
                "format": fmt,
            }
        )

    if not clean["kpis"]:
        clean["kpis"] = fallback_kpis(profile)

    for chart in spec.get("charts") or []:
        if len(clean["charts"]) >= MAX_CHARTS:
            dropped.append({"item": "chart", "reason": "over the 6-chart limit"})
            break
        valid, reason = _validate_chart(chart, cols)
        if valid is None:
            dropped.append(
                {
                    "item": (chart.get("title") if isinstance(chart, dict) else None) or "chart",
                    "reason": reason,
                }
            )
            continue
        clean["charts"].append(valid)

    for column in spec.get("filters") or []:
        if len(clean["filters"]) >= MAX_FILTERS:
            break
        if column in cols and cols[column]["kind"] in ("categorical", "boolean", "date"):
            if column not in clean["filters"]:
                clean["filters"].append(column)
        else:
            dropped.append({"item": column, "reason": "filter must be categorical or date"})

    return clean, dropped


def plan_dashboard(profile: dict, focus: str | None = None) -> tuple[dict, dict]:
    """Ask the model for a spec; validate it; fall back when unusable.

    Returns ``(spec, meta)`` where meta carries fallback/dropped/token info.
    """
    from groq import Groq

    from agent.config import settings
    from agent.observability import get_logger

    logger = get_logger()
    client = Groq(api_key=settings.groq_api_key)

    started = time.time()
    tokens = 0
    raw_error = None
    parsed = None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(profile, focus)},
    ]

    for _attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.model,
                messages=messages,
                temperature=0.2,
            )
            tokens += response.usage.total_tokens
            parsed = parse_json(response.choices[0].message.content or "")
            break
        except Exception as exc:  # bad JSON or API error; retry once
            raw_error = f"{type(exc).__name__}: {exc}"

    clean, dropped = (validate_spec(parsed, profile) if parsed else (None, []))
    used_fallback = not clean or not clean["charts"]
    if used_fallback:
        clean = fallback_spec(profile)

    meta = {
        "fallback": used_fallback,
        "dropped": dropped,
        "tokens": tokens,
        "latency_s": round(time.time() - started, 2),
        "error": raw_error,
        "focus": (focus or "").strip() or None,
    }

    logger.info(
        json.dumps(
            {
                "kind": "dashboard",
                "spec": clean,
                "dropped": dropped,
                "fallback": used_fallback,
                "latency_s": meta["latency_s"],
                "tokens": tokens,
                "error": raw_error,
                "focus": meta["focus"],
            }
        )
    )
    return clean, meta
