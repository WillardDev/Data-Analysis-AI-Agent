import sys
import pandas as pd
from .agent import ask

USAGE = 'usage: python -m agent.main <csv> "<question>"'

if __name__ == "__main__":
    if len(sys.argv) < 3 or not sys.argv[2].strip():
        sys.exit(USAGE)
    df = pd.read_csv(sys.argv[1])
    answer, _ = ask(sys.argv[2], df)
    print(answer)
