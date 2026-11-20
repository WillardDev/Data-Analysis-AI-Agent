"""Render a dashboard spec into Plotly figures and KPI values.

Everything here is local and deterministic: filters and re-renders never call
the model. Charts that cannot be built are reported, not raised.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .profile import looks_like_date, pretty_label

ACCENT = "#2563EB"
PALETTE = [ACCENT, "#0EA5E9", "#14B8A6", "#F59E0B", "#8B5CF6", "#EF4444", "#64748B"]
TEMPLATE = "plotly_white"
MAX_SCATTER_POINTS = 2000
MAX_TABLE_ROWS = 200


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def format_compact(value, fmt: str = "number") -> str:
    """Format 1200 as 1.2K and 3400000 as 3.4M."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"

    if fmt == "percent":
        number = float(value)
        if abs(number) <= 1:
            number *= 100
        return f"{number:,.1f}%"

    prefix = "$" if fmt == "currency" else ""
    number = float(value)
    magnitude = abs(number)

    if magnitude >= 1e9:
        body = f"{number / 1e9:,.1f}B"
    elif magnitude >= 1e6:
        body = f"{number / 1e6:,.1f}M"
    elif magnitude >= 1e3:
        body = f"{number / 1e3:,.1f}K"
    elif magnitude >= 100 or float(number).is_integer():
        body = f"{number:,.0f}"
    elif magnitude >= 1:
        body = f"{number:,.2f}".rstrip("0").rstrip(".")
    else:
        body = f"{number:.3g}"
    return f"{prefix}{body}"


def _style(fig, height: int = 380):
    fig.update_layout(
        template=TEMPLATE,
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        colorway=PALETTE,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        font=dict(family="system-ui, -apple-system, sans-serif", size=13),
        hoverlabel=dict(bgcolor="white"),
    )
    return fig


# --------------------------------------------------------------------------- #
# Filtering and aggregation
# --------------------------------------------------------------------------- #
def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply sidebar filters locally. Date ranges are ``(start, end)`` tuples."""
    out = df
    for column, value in (filters or {}).items():
        if value in (None, [], ()) or column not in out.columns:
            continue
        if isinstance(value, tuple) and len(value) == 2:
            dates = pd.to_datetime(out[column], errors="coerce")
            start, end = pd.Timestamp(value[0]), pd.Timestamp(value[1])
            out = out[(dates >= start) & (dates <= end + pd.Timedelta(days=1))]
        elif isinstance(value, (list, tuple, set)):
            if not value:
                continue
            out = out[out[column].astype(str).isin([str(v) for v in value])]
        else:
            out = out[out[column] == value]
    return out


def _aggregate(series: pd.Series, agg: str):
    if agg == "count":
        return series.size
    series = series.dropna()
    if series.empty:
        return float("nan")
    if agg == "mean":
        return series.mean()
    if agg == "median":
        return series.median()
    return series.sum()


def _grouped(df: pd.DataFrame, keys, value: str | None, agg: str) -> pd.Series:
    if isinstance(keys, str):
        keys = [keys]
    grouped = df.groupby(keys, dropna=False)
    if agg == "count" or value is None:
        result = grouped.size()
    else:
        result = grouped[value].apply(lambda s: _aggregate(s, agg))
    result.name = "value"
    return result


def _category_table(df: pd.DataFrame, x: str, y: str | None, agg: str, top_n: int) -> pd.DataFrame:
    series = _grouped(df, x, y, agg).sort_values(ascending=False)
    if len(series) > top_n:
        head = series.head(top_n)
        rest = series.iloc[top_n:]
        series = pd.concat([head, pd.Series({"Other": rest.sum()}, name="value")])
    table = series.reset_index()
    table.columns = [x, "value"]
    return table


def _date_table(df: pd.DataFrame, x: str, y: str, agg: str, color: str | None) -> pd.DataFrame:
    data = df[[c for c in (x, y, color) if c]].copy()
    data[x] = pd.to_datetime(data[x], errors="coerce")
    data = data.dropna(subset=[x])
    if data.empty:
        return pd.DataFrame(columns=[x, "value"])

    span_days = (data[x].max() - data[x].min()).days
    period = "W" if span_days <= 120 else "M"
    data["_period"] = data[x].dt.to_period(period).dt.start_time

    keys = ["_period"] + ([color] if color else [])
    series = _grouped(data, keys, y, agg).reset_index()
    series = series.rename(columns={"_period": x})
    return series.sort_values(x)


# --------------------------------------------------------------------------- #
# Insights
# --------------------------------------------------------------------------- #
def _insight_for(chart: dict, table: pd.DataFrame | None, value_fmt: str = "number") -> str:
    if chart.get("insight"):
        return chart["insight"]
    if table is None or table.empty:
        return ""

    ctype = chart["type"]
    try:
        if ctype in ("bar", "hbar", "pie") and "value" in table:
            ranked = table.sort_values("value", ascending=False)
            top = ranked.iloc[0]
            share = ""
            total = table["value"].sum()
            if ctype == "pie" and total:
                share = f" ({top['value'] / total:.0%} of the total)"
            if str(top.iloc[0]) == "Other":
                return (
                    f"The combined remaining categories total "
                    f"{format_compact(top['value'], value_fmt)}."
                )
            return (
                f"{top.iloc[0]} leads with {format_compact(top['value'], value_fmt)}{share}."
            )
        if ctype == "line" and "value" in table:
            first, last = table.iloc[0], table.iloc[-1]
            if first["value"]:
                change = (last["value"] - first["value"]) / abs(first["value"]) * 100
                direction = "rose" if change >= 0 else "fell"
                return (
                    f"{format_compact(last['value'], value_fmt)} at the latest point, "
                    f"{direction} {abs(change):.0f}% from the start."
                )
            return f"Latest value: {format_compact(last['value'], value_fmt)}."
        if ctype == "scatter" and len(table) > 2:
            x, y = chart.get("x"), chart.get("y")
            if x in table and y in table:
                corr = table[x].corr(table[y])
                if pd.notna(corr):
                    strength = "strong" if abs(corr) >= 0.6 else "moderate" if abs(corr) >= 0.3 else "weak"
                    return f"{strength.capitalize()} {('positive' if corr > 0 else 'negative')} relationship (r = {corr:.2f})."
        if ctype == "histogram" and chart.get("x") in table:
            series = table[chart["x"]].dropna()
            if not series.empty:
                return (
                    f"Median {format_compact(series.median(), value_fmt)}, "
                    f"mean {format_compact(series.mean(), value_fmt)}."
                )
        if ctype == "stacked_bar" and "value" in table:
            top = table.sort_values("value", ascending=False).iloc[0]
            label = " / ".join(
                str(top[column])
                for column in (chart.get("x"), chart.get("color"))
                if column in table
            )
            return f"{label} is the largest segment at {format_compact(top['value'], value_fmt)}."
        if ctype == "box":
            group = chart.get("color") or chart.get("x")
            measure = chart.get("y")
            if group in table and measure in table:
                medians = (
                    table[[group, measure]]
                    .dropna()
                    .groupby(group)[measure]
                    .median()
                    .sort_values(ascending=False)
                )
                if not medians.empty:
                    return (
                        f"{medians.index[0]} has the highest median "
                        f"{pretty_label(measure)} at {format_compact(medians.iloc[0], value_fmt)}."
                    )
    except Exception:
        return ""
    return ""


# --------------------------------------------------------------------------- #
# KPI cards
# --------------------------------------------------------------------------- #
def _kpi_value(df: pd.DataFrame, column: str, agg: str):
    if agg == "count":
        return float(len(df))
    if column not in df.columns:
        return None
    value = _aggregate(df[column], agg)
    return None if pd.isna(value) else float(value)


def _period_delta(df: pd.DataFrame, column: str, agg: str, date_col: str | None):
    if not date_col or date_col not in df.columns:
        return None
    dates = pd.to_datetime(df[date_col], errors="coerce")
    if dates.notna().sum() < 4:
        return None
    cutoff = dates.min() + (dates.max() - dates.min()) / 2
    current = _kpi_value(df[dates > cutoff], column, agg)
    previous = _kpi_value(df[dates <= cutoff], column, agg)
    if not current or not previous:
        return None
    return (current - previous) / abs(previous) * 100


def kpi_cards(spec: dict, df: pd.DataFrame, date_col: str | None = None) -> list[dict]:
    cards = []
    for kpi in spec.get("kpis", []):
        value = _kpi_value(df, kpi["column"], kpi.get("agg", "sum"))
        cards.append(
            {
                "label": kpi.get("label", pretty_label(kpi["column"])),
                "value": format_compact(value, kpi.get("format", "number")),
                "delta": _period_delta(df, kpi["column"], kpi.get("agg", "sum"), date_col),
                "raw": value,
            }
        )
    return cards


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _build_figure(chart: dict, df: pd.DataFrame) -> tuple[go.Figure | None, pd.DataFrame | None]:
    ctype = chart["type"]
    x, y, color = chart.get("x"), chart.get("y"), chart.get("color")
    agg = chart.get("agg", "sum")
    top_n = chart.get("top_n", 10)

    if ctype in ("bar", "hbar", "pie"):
        table = _category_table(df, x, y, agg, top_n)
        if ctype == "pie":
            if len(table) > 5:
                ctype = "bar"
            else:
                fig = px.pie(table, names=x, values="value", title=chart["title"], hole=0.45)
                return _style(fig), table
        if ctype == "hbar":
            table = table.sort_values("value")
            fig = px.bar(
                table, x="value", y=x, orientation="h", title=chart["title"],
                labels={"value": pretty_label(y or "Count")},
            )
        else:
            fig = px.bar(
                table, x=x, y="value", title=chart["title"],
                labels={"value": pretty_label(y or "Count")},
            )
        return _style(fig), table

    if ctype == "line":
        table = _date_table(df, x, y, agg, color)
        fig = px.line(
            table, x=x, y="value", color=color, markers=True, title=chart["title"],
            labels={"value": pretty_label(y)},
        )
        return _style(fig), table

    if ctype == "stacked_bar":
        keys = [x] + ([color] if color else [])
        table = _grouped(df, keys, y, agg).reset_index()
        fig = px.bar(
            table, x=x, y="value", color=color, barmode="stack", title=chart["title"],
            labels={"value": pretty_label(y)},
        )
        return _style(fig), table

    if ctype == "scatter":
        data = df[[c for c in (x, y, color) if c]].dropna()
        if len(data) > MAX_SCATTER_POINTS:
            data = data.sample(MAX_SCATTER_POINTS, random_state=0)
        fig = px.scatter(data, x=x, y=y, color=color, title=chart["title"], opacity=0.7)
        return _style(fig), data

    if ctype == "histogram":
        data = df[[x]].dropna()
        fig = px.histogram(data, x=x, nbins=30, title=chart["title"])
        return _style(fig), data

    if ctype == "box":
        group = color or x
        data = df[[c for c in (group, y) if c]].dropna()
        fig = px.box(data, x=group, y=y, title=chart["title"])
        return _style(fig), data

    if ctype == "heatmap":
        pivot = pd.crosstab(df[x], df[y])
        fig = go.Figure(
            go.Heatmap(
                z=pivot.values,
                x=[str(c) for c in pivot.columns],
                y=[str(i) for i in pivot.index],
                colorscale="Blues",
            )
        )
        fig.update_layout(title=chart["title"], xaxis_title=pretty_label(x), yaxis_title=pretty_label(y))
        return _style(fig), pivot.reset_index()

    if ctype == "table":
        columns = [c for c in (x, y, color) if c]
        table = df[columns].head(MAX_TABLE_ROWS) if columns else df.head(MAX_TABLE_ROWS)
        return None, table

    raise ValueError(f"unsupported chart type {ctype}")


def build_dashboard(spec: dict, df: pd.DataFrame) -> dict:
    """Return KPI cards and rendered charts. Bad charts are skipped, not raised."""
    date_col = None
    for column in spec.get("filters", []):
        if column in df.columns and looks_like_date(df[column]):
            date_col = column
            break
    if date_col is None and spec.get("charts"):
        for chart in spec["charts"]:
            if chart["type"] == "line" and chart.get("x"):
                date_col = chart["x"]
                break

    result = {"kpis": kpi_cards(spec, df, date_col), "charts": []}

    for chart in spec.get("charts", []):
        try:
            figure, table = _build_figure(chart, df)
            value_fmt = "currency" if any(
                k["column"] == chart.get("y") and k.get("format") == "currency"
                for k in spec.get("kpis", [])
            ) else "number"
            result["charts"].append(
                {
                    "chart": chart,
                    "figure": figure,
                    "table": table,
                    "insight": _insight_for(chart, table, value_fmt),
                    "error": None,
                }
            )
        except Exception as exc:
            result["charts"].append(
                {
                    "chart": chart,
                    "figure": None,
                    "table": None,
                    "insight": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return result
