"""Tests for dashboard profiling, spec validation, fallback and rendering."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import planner, profile, render  # noqa: E402


@pytest.fixture
def df() -> pd.DataFrame:
    rows = 40
    return pd.DataFrame(
        {
            "order_id": [f"ORD-{i}" for i in range(rows)],
            "date": pd.date_range("2026-01-01", periods=rows, freq="D"),
            "product": ["A", "B", "C", "D", "E", "F"] * 6 + ["A"] * 4,
            "region": ["North", "South"] * 20,
            "revenue": [i * 10.0 for i in range(rows)],
            "quantity": [i % 5 for i in range(rows)],
        }
    )


def test_profile_detects_kinds_and_ids(df):
    prof = profile.profile_dataframe(df)
    kinds = {col["name"]: col["kind"] for col in prof["columns"]}
    ids = {col["name"]: col["is_id"] for col in prof["columns"]}

    assert kinds["date"] == "date"
    assert kinds["revenue"] == "numeric"
    assert kinds["product"] == "categorical"
    assert ids["order_id"] is True
    assert prof["date_range"]["column"] == "date"
    assert prof["rows"] == 40


def test_parse_json_tolerates_markdown_fences():
    spec = planner.parse_json('```json\n{"title": "x", "charts": []}\n```')
    assert spec["title"] == "x"


def test_validate_drops_unknown_columns(df):
    prof = profile.profile_dataframe(df)
    spec = {
        "title": "T",
        "charts": [{"type": "bar", "x": "missing_col", "y": "revenue", "agg": "sum"}],
        "kpis": [],
    }
    clean, dropped = planner.validate_spec(spec, prof)

    assert clean["charts"] == []
    assert dropped
    assert "missing_col" in dropped[0]["reason"]


def test_validate_drops_incompatible_chart_type(df):
    prof = profile.profile_dataframe(df)
    spec = {
        "charts": [{"type": "line", "x": "product", "y": "revenue"}],
        "kpis": [],
    }
    clean, dropped = planner.validate_spec(spec, prof)

    assert clean["charts"] == []
    assert "date x" in dropped[0]["reason"]


def test_unique_numeric_measure_is_not_an_id(df):
    prof = profile.profile_dataframe(df)
    ids = {col["name"]: col["is_id"] for col in prof["columns"]}

    assert ids["order_id"] is True
    assert ids["revenue"] is False
    assert "revenue" in profile.usable_columns(prof, "numeric")


def test_swapped_axes_are_repaired(df):
    prof = profile.profile_dataframe(df)
    spec = {
        "charts": [{"type": "hbar", "x": "revenue", "y": "product", "agg": "sum"}],
        "kpis": [],
    }
    clean, dropped = planner.validate_spec(spec, prof)

    assert dropped == []
    assert clean["charts"][0]["x"] == "product"
    assert clean["charts"][0]["y"] == "revenue"


def test_pie_is_downgraded_when_too_many_slices(df):
    prof = profile.profile_dataframe(df)
    spec = {
        "charts": [{"type": "pie", "x": "product", "y": "revenue", "agg": "sum"}],
        "kpis": [],
    }
    clean, _ = planner.validate_spec(spec, prof)

    assert len(clean["charts"]) == 1
    assert clean["charts"][0]["type"] == "bar"


def test_chart_count_is_capped(df):
    prof = profile.profile_dataframe(df)
    spec = {
        "charts": [
            {"type": "bar", "x": "product", "y": "revenue", "agg": "sum"}
            for _ in range(10)
        ],
        "kpis": [],
    }
    clean, dropped = planner.validate_spec(spec, prof)

    assert len(clean["charts"]) == planner.MAX_CHARTS
    assert any("6-chart limit" in item["reason"] for item in dropped)


def test_filters_must_be_categorical_or_date(df):
    prof = profile.profile_dataframe(df)
    clean, dropped = planner.validate_spec(
        {"charts": [], "kpis": [], "filters": ["revenue", "region", "date", "product", "quantity"]},
        prof,
    )

    assert clean["filters"] == ["region", "date", "product"]
    assert any(item["item"] == "revenue" for item in dropped)


def test_fallback_spec_is_usable(df):
    prof = profile.profile_dataframe(df)
    spec = planner.fallback_spec(prof)

    assert spec["charts"]
    assert len(spec["charts"]) <= planner.MAX_CHARTS
    assert spec["kpis"]

    names = {col["name"] for col in prof["columns"]}
    for chart in spec["charts"]:
        for key in ("x", "y", "color"):
            assert chart[key] is None or chart[key] in names


def test_render_builds_figures_and_insights(df):
    prof = profile.profile_dataframe(df)
    spec = planner.fallback_spec(prof)

    result = render.build_dashboard(spec, df)

    assert result["kpis"]
    assert result["charts"]
    assert any(item["figure"] is not None for item in result["charts"])
    assert all(item["error"] is None for item in result["charts"])
    assert any(item["insight"] for item in result["charts"])


def test_filters_apply_locally(df):
    filtered = render.apply_filters(df, {"region": ["North"]})
    assert set(filtered["region"]) == {"North"}
    assert len(filtered) < len(df)


def test_insight_uses_real_numbers(df):
    prof = profile.profile_dataframe(df)
    spec = {
        "title": "T",
        "subtitle": "",
        "kpis": [],
        "charts": [{"type": "hbar", "x": "product", "y": "revenue", "agg": "sum", "insight": ""}],
        "filters": [],
    }
    clean, _ = planner.validate_spec(spec, prof)
    result = render.build_dashboard(clean, df)

    insight = result["charts"][0]["insight"]
    assert insight
    assert "leads with" in insight
