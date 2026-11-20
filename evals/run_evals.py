import json, sys
import pandas as pd
sys.path.insert(0, "src")
from agent.agent import ask

df = pd.read_csv(sys.argv[1])
cases = json.load(open("evals/cases.json"))
passed = 0
for c in cases:
    answer, _ = ask(c["question"], df)
    ok = c["expected"] in (answer or "").replace(",", "")
    passed += ok
    print(("PASS" if ok else "FAIL"), "-", c["question"])
print(f"\n{passed}/{len(cases)} passed")
