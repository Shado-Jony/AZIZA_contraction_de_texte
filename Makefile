.PHONY: install test test-all lint run docker-build docker-run clean

install:
	pip install -r requirements.txt

test:
	python tests.py

test-all:
	python tests.py all

lint:
	ruff check aziza/ demo/ tests.py

run:
	python demo/app.py

docker-build:
	docker compose build

docker-run:
	docker compose up

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
