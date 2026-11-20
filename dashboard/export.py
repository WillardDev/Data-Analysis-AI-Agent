"""Export a dashboard to JSON, CSV, Excel, HTML, PNG, PDF and Hyper.

Every function returns bytes and raises nothing the caller must handle:
the app checks :func:`availability` and shows a reason when a format is
unavailable instead of crashing.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .profile import pretty_label
from .render import format_compact

_PNG_OK: bool | None = None


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def _can_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def png_supported() -> bool:
    """Render one tiny figure once; kaleido also needs a Chrome binary."""
    global _PNG_OK
    if _PNG_OK is None:
        try:
            import plotly.graph_objects as go

            probe = go.Figure(go.Bar(x=["a"], y=[1]))
            _PNG_OK = bool(probe.to_image(format="png"))
        except Exception:
            _PNG_OK = False
    return bool(_PNG_OK)


def availability() -> dict[str, tuple[bool, str]]:
    has_png = png_supported()
    return {
        "png": (has_png, "Needs kaleido and a Chrome/Chromium binary."),
        "pdf": (has_png and _can_import("fpdf"), "Needs fpdf2 and PNG rendering."),
        "html": (True, ""),
        "excel": (_can_import("openpyxl"), "Needs openpyxl."),
        "csv": (True, ""),
        "hyper": (
            _can_import("tableauhyperapi"),
            "Needs tableauhyperapi (x86_64 Linux/Windows only).",
        ),
        "json": (True, ""),
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _safe_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", str(name))[:31] or "Sheet"
    candidate, index = cleaned, 2
    while candidate in used:
        suffix = f" {index}"
        candidate = cleaned[: 31 - len(suffix)] + suffix
        index += 1
    used.add(candidate)
    return candidate


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "chart"


def _tables_as_list(charts: list[dict]) -> list[tuple[str, pd.DataFrame]]:
    tables = []
    for index, item in enumerate(charts, start=1):
        table = item.get("table")
        if isinstance(table, pd.DataFrame) and not table.empty:
            tables.append((f"Chart {index} - {item['chart'].get('title', '')}", table))
    return tables


# --------------------------------------------------------------------------- #
# Formats
# --------------------------------------------------------------------------- #
def to_json(spec: dict) -> bytes:
    return json.dumps(spec, indent=2, ensure_ascii=False).encode("utf-8")


def to_csv_zip(df: pd.DataFrame, charts: list[dict]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.csv", df.to_csv(index=False))
        for index, (name, table) in enumerate(_tables_as_list(charts), start=1):
            archive.writestr(f"chart-{index}-{_slug(name)}.csv", table.to_csv(index=False))
    return buffer.getvalue()


def to_excel(df: pd.DataFrame, charts: list[dict], kpis: list[dict], spec: dict) -> bytes:
    buffer = io.BytesIO()
    used: set[str] = set()
    summary = pd.DataFrame(
        [
            {
                "KPI": card["label"],
                "Value": card["value"],
                "Change vs previous period": (
                    f"{card['delta']:+.1f}%" if card.get("delta") is not None else ""
                ),
            }
            for card in kpis
        ]
    )
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name=_safe_sheet_name("Summary", used), index=False)
        df.to_excel(writer, sheet_name=_safe_sheet_name("Data", used), index=False)
        for name, table in _tables_as_list(charts):
            table.to_excel(writer, sheet_name=_safe_sheet_name(name, used), index=False)
    return buffer.getvalue()


def to_html(spec: dict, charts: list[dict], kpis: list[dict]) -> bytes:
    cards = "".join(
        f'<div class="kpi"><div class="label">{card["label"]}</div>'
        f'<div class="value">{card["value"]}</div>'
        + (
            f'<div class="delta">{card["delta"]:+.1f}% vs previous period</div>'
            if card.get("delta") is not None
            else ""
        )
        + "</div>"
        for card in kpis
    )

    blocks = []
    for index, item in enumerate(charts):
        if item.get("figure") is None:
            continue
        blocks.append(
            '<section class="chart">'
            + item["figure"].to_html(
                full_html=False,
                include_plotlyjs=True if not blocks else False,
                config={"displayModeBar": True, "responsive": True},
            )
            + f'<p class="insight">{item.get("insight", "")}</p>'
            + "</section>"
        )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{spec.get("title", "Dashboard")}</title>
<style>
 body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
 header {{ padding: 32px 40px 8px; }}
 h1 {{ margin: 0 0 4px; font-size: 26px; }}
 .subtitle {{ color: #64748b; margin: 0; }}
 .kpis {{ display: flex; gap: 16px; padding: 24px 40px; flex-wrap: wrap; }}
 .kpi {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 20px; min-width: 180px; }}
 .kpi .label {{ color: #64748b; font-size: 13px; }}
 .kpi .value {{ font-size: 26px; font-weight: 600; margin-top: 4px; }}
 .kpi .delta {{ color: #2563eb; font-size: 12px; margin-top: 4px; }}
 .chart {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; margin: 0 40px 20px; padding: 12px; }}
 .insight {{ color: #475569; font-size: 14px; margin: 4px 8px 8px; }}
 footer {{ color: #64748b; font-size: 12px; padding: 16px 40px 40px; }}
</style></head>
<body>
<header><h1>{spec.get("title", "Dashboard")}</h1><p class="subtitle">{spec.get("subtitle", "")}</p></header>
<div class="kpis">{cards}</div>
{"".join(blocks)}
<footer>Generated by AI from your data. Verify important numbers.</footer>
</body></html>"""
    return html.encode("utf-8")


def chart_png(fig) -> bytes | None:
    try:
        return fig.to_image(format="png", scale=2)
    except Exception:
        return None


def dashboard_png(pngs: list[bytes]) -> bytes | None:
    """Stack chart images vertically into one dashboard image."""
    images = [png for png in pngs if png]
    if not images:
        return None
    try:
        from PIL import Image

        loaded = [Image.open(io.BytesIO(png)).convert("RGB") for png in images]
        width = max(image.width for image in loaded)
        gap = 24
        height = sum(image.height for image in loaded) + gap * (len(loaded) - 1)
        canvas = Image.new("RGB", (width, height), "white")
        offset = 0
        for image in loaded:
            canvas.paste(image, ((width - image.width) // 2, offset))
            offset += image.height + gap
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None


def _latin(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def to_pdf(spec: dict, kpis: list[dict], pngs: list[bytes]) -> bytes | None:
    try:
        from fpdf import FPDF
    except Exception:
        return None

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _latin(spec.get("title", "Dashboard")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(0, 5, _latin(spec.get("subtitle", "")))
    pdf.ln(4)

    pdf.set_text_color(15, 23, 42)
    for card in kpis:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(60, 8, _latin(f"{card['label']}: {card['value']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    for png in pngs:
        if not png:
            continue
        try:
            pdf.image(io.BytesIO(png), w=180)
            pdf.ln(4)
        except Exception:
            continue

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(0, 4, "Generated by AI from your data. Verify important numbers.")
    return bytes(pdf.output())


def to_hyper(df: pd.DataFrame) -> bytes | None:
    """Write a Tableau Hyper extract (x86_64 Linux/Windows wheels only)."""
    try:
        from tableauhyperapi import (
            Connection,
            CreateMode,
            HyperProcess,
            Inserter,
            SqlType,
            TableDefinition,
            Telemetry,
        )
    except Exception:
        return None

    def sql_type(series: pd.Series):
        if pd.api.types.is_datetime64_any_dtype(series):
            return SqlType.date()
        if pd.api.types.is_bool_dtype(series):
            return SqlType.bool()
        if pd.api.types.is_numeric_dtype(series):
            return SqlType.double()
        return SqlType.text()

    def value(item):
        if item is None or (isinstance(item, float) and pd.isna(item)):
            return None
        if isinstance(item, (pd.Timestamp, datetime)):
            return item.date()
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            return float(item)
        return str(item)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "extract.hyper"
        with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
            with Connection(hyper.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as conn:
                definition = TableDefinition(
                    "Extract",
                    [
                        TableDefinition.Column(str(col), sql_type(df[col]))
                        for col in df.columns
                    ],
                )
                conn.catalog.create_table(definition)
                rows = [tuple(value(v) for v in row) for row in df.itertuples(index=False)]
                with Inserter(conn, definition) as inserter:
                    inserter.add_rows(rows)
                    inserter.execute()
        return path.read_bytes()


def to_tableau_notes() -> str:
    return (
        "Tableau and Power BI cannot import a finished Plotly layout. "
        "These exports carry the data; rebuild the visuals there."
    )
