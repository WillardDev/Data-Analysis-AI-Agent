install:
	pip install -r requirements.txt
test:
	pytest tests/
eval:
	python evals/run_evals.py data/sales.csv
run:
	python -m agent.main data/sales.csv "$(Q)"
docker:
	docker compose run --rm agent data/sales.csv "$(Q)"
