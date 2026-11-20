import sys
import pandas as pd
from .agent import ask

if __name__ == "__main__":
    df = pd.read_csv(sys.argv[1])
    answer, _ = ask(sys.argv[2], df)
    print(answer)
