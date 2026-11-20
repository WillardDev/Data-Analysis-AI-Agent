# Data Analysis Agent

> Ask questions about your data in plain English. The agent writes the code, runs it, draws the charts, and explains the results.

## The Problem

Most people who own data cannot query it. A shop owner has a sales CSV, a clinic has patient visit records, a farmer's cooperative has yield spreadsheets, but answering a simple question like *"Which products sold worst last quarter?"* still means finding someone who knows pandas or SQL.

This project builds an **AI agent** that closes that gap.

## What It Does

You load a dataset and ask a question. The agent then works in a loop:

1. **Reads** a summary of your data (columns, types, sample rows)
2. **Writes** Python (pandas, matplotlib) to answer the question
3. **Runs** the code and looks at the output
4. **Fixes** its own mistakes if the code errors
5. **Explains** the result in plain English, based only on what the code actually printed

Example questions:

- "Which 5 products sold worst last quarter?"
- "Plot monthly revenue and tell me if there's a trend."
- "Are there missing values or outliers I should worry about?"
- "Now break that down by region." *(follow-ups keep context)*

## Why an Agent, Not Just a Chatbot?

A chatbot guesses at answers from its training data. This agent **does the work**: it computes on your real data, so every number in its answer is traceable to code you can read. If its first attempt fails (a wrong column name, a bad date format), it reads the error and tries again, which is what makes it an agent rather than a one-shot text generator.

## How This Notebook Is Organized

This is not a flat pile of cells. The notebook is structured as a **production-grade project in seven layers**, each with one job. Some layers are code you run; others use `%%writefile` cells to generate the real project files on disk, so running the notebook top to bottom produces a proper repository.

| # | Layer | Job | What it produces |
|---|-------|-----|------------------|
| 1 | **Foundation** | Project identity, dependencies, docs | Folder structure, `requirements.txt`, `README.md`, `LICENSE` |
| 2 | **Configuration** | Environment-specific secrets and settings | `.env.example`, `.gitignore`, `config.py` |
| 3 | **Source** | The actual agent logic | `tools.py`, `prompts.py`, `agent.py`, `main.py` |
| 4 | **Containerization** | Ship and run anywhere | `Dockerfile`, `docker-compose.yml` |
| 5 | **Observability** | See what it is doing | Structured JSON logs of every question, step, error, and token count |
| 6 | **Evaluation** | Prove it works, before and after every change | Test questions with known answers, unit tests |
| 7 | **Tooling & Automation** | CI/CD, editor config, scripts | GitHub Actions workflow, `Makefile`, `.editorconfig` |

## Tech Stack

- **Language:** Python 3.12
- **Model:** Llama 3.3 70B via the [Groq](https://console.groq.com/keys) API (free tier available, supports tool calling)
- **Data:** pandas, matplotlib (DuckDB planned for SQL)
- **Config:** python-dotenv, pydantic-settings
- **Quality:** pytest, GitHub Actions
- **Packaging:** Docker

The model is swappable. Changing the client and model name in Layer 2 and Layer 3 is enough to move to Claude, OpenAI, or a local model.

## Before You Start

1. Create a free API key at **console.groq.com/keys**
2. Have a CSV ready to analyze (any tabular data works)
3. Python 3.10+ and Jupyter installed

## A Note on Safety

The agent executes code that the model writes. In a personal notebook with data you trust, that is fine, but **`exec()` is not a sandbox**: the code runs with the same access as your Python session. Layer 4 (Docker) is what contains it. Do not expose this agent to other users without running it inside a container or a dedicated sandbox.

## Roadmap

- [ ] Add a SQL tool (DuckDB) so the agent can choose between pandas and SQL
- [ ] File upload widget for non-technical users
- [ ] A data-cleaning tool that describes its changes before applying them
- [ ] Larger evaluation set with real expected answers
- [ ] Hosted observability (Langfuse or LangSmith)

## Author

*Willard Odongo*