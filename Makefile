# Author: Silan Hu (silan.hu@u.nus.edu)

.PHONY: help sync lint test smoke

help:
	@echo "Targets: sync | lint | test | smoke"

sync:
	uv sync

lint:
	uv run ruff check easyremote tests gallery examples --output-format=full

test:
	uv run pytest -q

smoke:
	uv run python gallery/run_smoke_tests.py

