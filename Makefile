.PHONY: help install lint fmt types test check

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-9s\033[0m %s\n", $$1, $$2}'

install: ## Create the environment
	uv sync --all-groups

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Format and autofix
	uv run ruff format .
	uv run ruff check --fix .

types: ## Type-check (strict)
	uv run mypy

test: ## Run the tests
	uv run pytest -q

report: ## Regenerate REPORT.md from the corpus
	uv run eval-lens report

check: lint types test ## What CI runs
