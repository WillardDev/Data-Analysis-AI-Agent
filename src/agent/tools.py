import io, contextlib, traceback
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless-safe; charts are saved, not shown
import matplotlib.pyplot as plt

def run_python(code: str, df: pd.DataFrame) -> str:
    out = io.StringIO()
    env = {"df": df, "pd": pd, "plt": plt}
    try:
        with contextlib.redirect_stdout(out):
            exec(code, env)
        plt.savefig("logs/last_chart.png") if plt.get_fignums() else None
        plt.close("all")
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
