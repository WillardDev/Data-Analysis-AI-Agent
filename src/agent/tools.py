import io, os, contextlib, traceback
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

FIGURES = []   # every chart the agent makes lands here

def show_chart(fig):
    os.makedirs("logs", exist_ok=True)
    FIGURES.append(fig)
    path = "logs/last_chart.html"
    fig.write_html(path)          # saved for CLI / Docker / notebook use
    print(f"(chart saved to {path})")

show = show_chart                 # alias, in case the model calls show(fig)

def run_python(code: str, df: pd.DataFrame) -> str:
    out = io.StringIO()
    env = {"df": df, "pd": pd, "px": px, "go": go, "show_chart": show_chart, "show": show}
    try:
        with contextlib.redirect_stdout(out):
            exec(code, env)
    except Exception:
        return out.getvalue() + "\nERROR:\n" + traceback.format_exc(limit=2)
    return out.getvalue() or "(ran fine, nothing printed, use print())"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_python",
        "description": "Run Python against the DataFrame `df`. Returns printed output or an error.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
}]
