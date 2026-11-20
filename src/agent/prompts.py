import io

def describe_df(df):
    buf = io.StringIO()
    df.info(buf=buf)
    return f"{buf.getvalue()}\nSample rows:\n{df.head(3).to_string()}"

def build_system_prompt(df):
    return f"""You are a data analyst. A pandas DataFrame named `df` is loaded.
Answer by writing Python and calling run_python.
- Use print() to show results; you only see printed output.
- Charts: build with plotly express (`px`) and call `show_chart(fig)`.
  Do not call `fig.show()` - it does nothing in this environment.
- If code errors, read the error and fix it.
- Never invent numbers. Base answers only on tool output.
- End with a short plain-English explanation.

DataFrame info:
{describe_df(df)}"""
