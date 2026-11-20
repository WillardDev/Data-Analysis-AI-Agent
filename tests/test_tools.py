import sys; sys.path.insert(0, "src")
import pandas as pd
from agent.tools import run_python

def test_runs_code():
    df = pd.DataFrame({"a": [1, 2, 3]})
    assert "6" in run_python("print(df.a.sum())", df)

def test_reports_errors():
    df = pd.DataFrame({"a": [1]})
    assert "ERROR" in run_python("print(df.missing)", df)
