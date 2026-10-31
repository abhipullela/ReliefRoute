.PHONY: install test lint run
install:
	python -m pip install -e '.[dev,agent,telegram,db]'
test:
	pytest
lint:
	ruff check .
run:
	uvicorn api.main:app --reload
