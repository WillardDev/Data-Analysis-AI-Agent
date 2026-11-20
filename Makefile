PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: install test eval run docker

install:
	$(PY) -m pip install -r requirements.txt
test:
	$(PY) -m pytest tests/ -q
eval:
	$(PY) evals/run_evals.py data/sales.csv
run:
	$(PY) -m agent.main data/sales.csv "$(Q)"
docker:
	docker compose run --rm agent data/sales.csv "$(Q)"
