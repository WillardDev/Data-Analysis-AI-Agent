# Data Analysis Agent

[![CI](https://github.com/WillardDev/Data-Analysis-AI-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/WillardDev/Data-Analysis-AI-Agent/actions/workflows/ci.yml)

> Ask questions about your data in plain English. The agent writes the code, runs it, draws the charts, and explains the results. Or switch to the Dashboard tab and get a full dashboard from one click.

## The Problem

Most people who own data cannot query it. A shop owner has a sales CSV, a clinic has patient visit records, a farmer's cooperative has yield spreadsheets, but answering a simple question like *"Which products sold worst last quarter?"* still means finding someone who knows pandas or SQL.

This project builds an **AI agent** that closes that gap.

## What It Does

You load a dataset and ask a question. The agent then works in a loop:

1. **Reads** a summary of your data (columns, types, sample rows)
2. **Writes** Python (pandas, plotly) to answer the question
3. **Runs** the code and looks at the output
4. **Fixes** its own mistakes if the code errors
5. **Explains** the result in plain English, based only on what the code actually printed

Example questions:

- "Which 5 products sold worst last quarter?"
- "Plot monthly revenue and tell me if there's a trend."
- "Are there missing values or outliers I should worry about?"
- "Now break that down by region." *(follow-ups keep context)*

There is also a **Dashboard tab**: upload the same file, optionally type a focus such as *"regional performance"*, and the agent plans a dashboard of KPIs and charts. It returns only a JSON spec, never plotting code, and the app renders it with fixed templates.

## Why an Agent, Not Just a Chatbot?

A chatbot guesses at answers from its training data. This agent **does the work**: it computes on your real data, so every number in its answer is traceable to code you can read. If its first attempt fails (a wrong column name, a bad date format), it reads the error and tries again, which is what makes it an agent rather than a one-shot text generator.

## Quickstart

```bash
git clone https://github.com/WillardDev/Data-Analysis-AI-Agent.git
cd Data-Analysis-AI-Agent

python3 -m venv .venv          # Homebrew/system Python blocks global pip installs
make install                   # installs into .venv

cp .env.example .env           # then paste your key into GROQ_API_KEY
mkdir -p data && cp /path/to/your.csv data/sales.csv

make test
make run Q="How many rows are in the data?"
```

Get a free key at **console.groq.com/keys**.

> `data/` and `logs/` are gitignored, so a fresh clone has no dataset. Drop any CSV into `data/` and reference its path.

## Usage

Everything goes through the `Makefile`, which uses `.venv/bin/python` so you never have to activate the environment:

| Command | What it does |
|---|---|
| `make install` | Install `requirements.txt` into `.venv` |
| `make test` | Run the unit tests |
| `make eval` | Run the evaluation cases against `data/sales.csv` |
| `make run Q="..."` | Ask one question from the terminal |
| `make docker Q="..."` | Same, inside the container |
| `make ui` | Launch the Streamlit app at http://localhost:8501 |
| `make docker-ui` | Launch the Streamlit app in Docker |

`make run` and `make docker` require a question; without `Q` they print usage and exit instead of calling the API with an empty prompt.

You can also work in `AI_Agent.ipynb`, which builds the project layer by layer. Its cells use `%%writefile` to generate the real files on disk, so running it top to bottom regenerates the source, config, Docker, and CI files.

## User Interface

`app.py` is a Streamlit front end for people who do not write code.

**Locally**

```bash
make ui            # http://localhost:8501
```

**Docker**

```bash
make docker-ui     # builds the image and serves on http://localhost:8501
# or: docker compose up ui
```

The app reuses `src/agent` unchanged: it calls `ask()` and reads the JSONL trace the observability layer already writes, so no agent logic is duplicated.

**Sidebar** — CSV or Excel (`.xlsx`) upload, a data preview (row count, column count, dtypes, missing values), starter questions generated from your column names, **Clear conversation**, and a **Show the code the agent wrote** toggle (off by default).

**Main area** — two tabs: **Chat** and **Dashboard**. The Chat tab shows a transcript. Each answer leads with the finding, then an interactive Plotly chart with PNG download (HTML fallback if a static renderer is unavailable), then a collapsed **How I got this** section with the code and raw output.

| State | What the user sees |
|---|---|
| No file uploaded | "Upload a CSV in the sidebar to get started"; chat input disabled |
| Working | Status line: *Analysing* → *Writing and running code* → *Preparing chart* |
| Error or step limit | "I couldn't answer that reliably…"; tracebacks stay inside the expander |
| File over 25 MB | Warning; only a summary and three sample rows are sent to the model |
| Follow-up question | The same history is reused, so "now break that down by region" works |
| Export | Per-chart PNG download and a full conversation as Markdown |

**Safety** — the API key is read from `.env` and never rendered; uploads are held in memory only and never written to disk; Docker is the isolation boundary for `exec()`; every question, code step, error, latency, and token count still lands in `logs/agent.jsonl`. A permanent note reminds users that answers are AI-generated.

## Dashboard Tab

The Dashboard tab builds a dashboard from the same uploaded file. You click **Generate dashboard**, optionally type a focus, and the agent returns a JSON spec: title, subtitle, 3–4 KPIs, up to six charts, and up to three filters. It never writes plotting code for this tab, so there is no `exec()` and no sandbox.

`dashboard/` holds the four modules:

| Module | Job |
|---|---|
| `profile.py` | Column kinds, cardinality, missing rates, ranges, date span |
| `planner.py` | Prompt, JSON parsing, spec validation, rule-based fallback |
| `render.py` | Spec → Plotly figures, KPI cards, one-line insights |
| `export.py` | One function per export format |

**Flow** — the app profiles the data locally, sends only that profile plus three sample rows to the model, validates the returned spec, drops charts that reference missing columns or incompatible types, and renders with fixed templates. Bad JSON gets one retry, then a rule-based default dashboard. The spec, validation drops, latency, and tokens are logged to `logs/agent.jsonl` with `"kind": "dashboard"`.

**Layout** — header and data freshness, KPI cards, the main chart full width, a two-column grid with an insight under each chart, a collapsed data-quality section (missing values and IQR outliers), then a permanent "Generated by AI" footer.

**Interactivity** — sidebar filters update every KPI and chart locally and never call the model. A **Customize** expander can hide a chart or swap its type. The generated dashboard is cached in `st.session_state`, so switching tabs does not spend tokens.

**Excel upload** — `.xlsx` files are read with `openpyxl` and converted to CSV in the background; the converted file is offered as a download in the sidebar.

### Exports

The export panel builds files only when you click **Prepare export files**, because Streamlit needs the bytes before it can render a download button. If a library is missing, the button is disabled with the reason instead of crashing.

| Format | Contents | Library |
|---|---|---|
| **PNG** | Each chart, plus the full dashboard stacked into one image | Plotly + `kaleido` (needs Chrome/Chromium) |
| **PDF** | One printable page: header, KPIs, chart images, insights | `fpdf2` |
| **HTML** | Self-contained interactive dashboard, opens in any browser | Plotly `to_html` |
| **Excel** | Summary KPIs, filtered data, and one sheet per chart table | `openpyxl` |
| **CSV** | Filtered data plus each chart table, zipped | pandas |
| **Tableau** | The filtered data as a Hyper extract | `tableauhyperapi` |
| **Power BI** | Use the Excel and CSV exports | — |
| **JSON** | The dashboard spec, so it can be reloaded or shared | stdlib |

Tableau and Power BI cannot import a finished Plotly layout. What transfers is the **data** (Hyper, Excel, CSV); the visuals are rebuilt in those tools. The UI says this beside the buttons.

`tableauhyperapi` publishes wheels only for x86_64 Linux and Windows. It is installed behind an environment marker in `requirements.txt`, so macOS (including Apple silicon) installs still succeed and the Hyper button simply reports that it is unavailable.

## Configuration

Settings come from `.env` via `pydantic-settings` (`src/agent/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *required* | Groq API key |
| `MODEL` | `openai/gpt-oss-120b` | Any tool-calling model on Groq |
| `MAX_STEPS` | `6` | Tool-call budget per question |
| `LOG_LEVEL` | `INFO` | Logger verbosity |

Available models change over time. If you get a `404 model_not_found`, list what your key can use:

```bash
curl -s -H "Authorization: Bearer $GROQ_API_KEY" \
  https://api.groq.com/openai/v1/models | python3 -m json.tool
```

## How It Works

`src/agent/agent.py` is the loop:

1. Build a system prompt containing `df.info()` and three sample rows (`prompts.py`).
2. Send the conversation plus a `run_python` tool definition to the model.
3. If the model returns a tool call, execute the code against `df` in a fresh namespace and feed the printed output or traceback back as the tool result.
4. Repeat until the model answers without a tool call, or `MAX_STEPS` is exhausted.
5. Log the whole trace as one JSON line.

The model only ever sees **stdout** from the code it wrote — not return values, not charts. That is why the prompt insists on `print()`.

### Charts

Charts are built with plotly (`px` / `go`). The execution namespace exposes `show_chart(fig)`, which appends to `FIGURES` and writes `logs/last_chart.html`:

```python
fig = px.bar(df, x="category", y="revenue", title="Revenue by Category")
show_chart(fig)
```

The prompt explicitly tells the model not to call `fig.show()`, which silently does nothing in a headless CLI or container.

## Observability

`src/agent/observability.py` writes one JSON object per question to `logs/agent.jsonl`:

```json
{"question": "...", "steps": [{"code": "...", "result": "...", "latency_s": 0.8, "error": false}], "answer": "...", "tokens": 618}
```

`error: true` flags any step whose code raised, so you can grep for failing runs. Note the file is created empty on first import and only gains records once a question completes.

## Evaluation

`evals/cases.json` holds questions with known answers; `evals/run_evals.py` runs each one and checks that the expected value appears in the answer.

```bash
make eval
# PASS - How many rows are in the data?
# PASS - What is the total revenue?
# 2/2 passed
```

The match is a substring check after commas are stripped, so `46,269.26` matches `46269.26`. It is deliberately simple — good enough to catch regressions, not a substitute for a labelled benchmark. The expected values are tied to the sample dataset; if you swap in your own CSV, update `evals/cases.json` too.

## Docker

```bash
docker compose build
make docker Q="Plot revenue by category"
```

The image is `python:3.12-slim` with dependencies installed at build time. `docker-compose.yml` mounts `./data` read-only and `./logs` writable, so charts and logs land on your host.

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | What it proves |
|---|---|
| `test` | `requirements.txt` installs and the unit tests pass (pip cache enabled) |
| `docker` | The Dockerfile still builds, using GitHub Actions layer cache |

Concurrent runs on the same branch are cancelled, so a rapid series of pushes does not queue up stale builds.

**Releasing:** push a version tag and the `publish` job builds and pushes the image to GHCR:

```bash
git tag v1.0.0
git push --tags
# ghcr.io/willarddev/data-analysis-ai-agent:1.0.0
# ghcr.io/willarddev/data-analysis-ai-agent:sha-<commit>
```

No secrets are needed — the workflow uses the automatic `GITHUB_TOKEN` with `packages: write`. Evals are *not* run in CI because they call the Groq API (cost) and need `data/sales.csv`, which is gitignored.

## Project Structure

```
app.py              Streamlit UI (upload, chat, charts, export)
src/agent/
  agent.py          the tool-calling loop
  tools.py          run_python sandbox-ish executor, plotly chart helper
  prompts.py        system prompt + dataframe summary
  config.py         pydantic-settings from .env
  observability.py  JSONL logger
  main.py           CLI entry point
tests/              unit tests for the executor
evals/              questions with expected answers
data/               your CSVs (gitignored)
logs/               agent.jsonl + last_chart.html (gitignored)
AI_Agent.ipynb      the project, built layer by layer
Makefile            install / test / eval / run / docker
```

## Tech Stack

- **Language:** Python 3.12 (Docker image); 3.10+ locally
- **Model:** `openai/gpt-oss-120b` via the [Groq](https://console.groq.com/keys) API
- **Data:** pandas, plotly
- **UI:** Streamlit
- **Config:** python-dotenv, pydantic-settings
- **Quality:** pytest, GitHub Actions
- **Packaging:** Docker

The model is swappable: change `MODEL` in `.env`, or point the client in `agent.py` at another provider that supports tool calling.

## A Note on Safety

The agent executes code that the model writes. In a personal notebook with data you trust, that is fine, but **`exec()` is not a sandbox**: the code runs with the same access as your Python session. Layer 4 (Docker) is what contains it. Do not expose this agent to other users without running it inside a container or a dedicated sandbox.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `error: externally-managed-environment` | Use the venv (`python3 -m venv .venv`) instead of `pip3 install` |
| `.venv/bin/python: No such file or directory` (or `make: python: command not found`) | The venv doesn't exist yet — run `python3 -m venv .venv && make install` |
| `404 model_not_found` | The model was retired — list available models and update `MODEL` |
| `ValueError: Expected object or value` reading `logs/agent.jsonl` | The log is empty because no question has completed yet |
| `failed to connect to the docker API` | Start Docker Desktop or OrbStack (`open -a OrbStack`) |
| Charts missing | The model called `fig.show()` instead of `show_chart(fig)` |

## Roadmap

- [x] Plotly charts with HTML output
- [x] Streamlit UI with upload, chat, chart export, and Markdown reports
- [x] Docker image and compose setup
- [x] JSONL observability
- [x] CI with tests, Docker build, and tagged releases
- [ ] SQL tool (DuckDB) so the agent can choose between pandas and SQL
- [ ] Data-cleaning tool that describes its changes before applying them
- [ ] Larger evaluation set with real expected answers
- [ ] Hosted observability (Langfuse or LangSmith)

## Author

*Willard Odongo*
