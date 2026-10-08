.PHONY: help setup check lint test test-compat clean run scrape normalize parse-file dump \
	sync-agents check-agents
.DEFAULT_GOAL := help

PRE_COMMIT := uvx pre-commit@4.3.0
COMPAT_PYTHON := 3.13

##@ General

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Development

setup: ## Create the environment and install the git hooks (pre-commit + commit-msg); needs uv
	uv sync --locked
	$(PRE_COMMIT) install --install-hooks

check: lint test test-compat ## Everything to pass before finishing: hooks, then tests on 3.14 and 3.13

lint: ## Every hook in .pre-commit-config.yaml over the whole repo
	$(PRE_COMMIT) run --all-files --show-diff-on-failure

test: ## Tests with 100% line and branch coverage on the development Python (.python-version)
	uv run --locked pytest

test-compat: ## Tests on Python 3.13, the oldest the tool supports, in a throwaway env
	uv run --isolated --python $(COMPAT_PYTHON) --no-default-groups --group test pytest -p no:cacheprovider

clean: ## Remove caches and coverage reports (keeps .venv and data/)
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml coverage.json dist build

##@ CLI (needs the phone for run, scrape and dump)

run: ## Run the CLI with ARGS, e.g. make run ARGS="run --days 3"
	uv run maps-timeline $(ARGS)

scrape: ## Walk the Timeline with ARGS, e.g. make scrape ARGS="--days 7"
	uv run maps-timeline scrape $(ARGS)

normalize: ## Rebuild the clean dataset with ARGS, e.g. make normalize ARGS="--geocode"
	uv run maps-timeline normalize $(ARGS)

parse-file: ## Parse a saved dump offline: make parse-file FILE=dump.xml
	@test -n "$(FILE)" || (echo "FILE is required, e.g. make parse-file FILE=dump.xml" && exit 1)
	uv run maps-timeline parse-file "$(FILE)"

dump: ## Save the current screen: make dump OUT=dump.xml
	uv run maps-timeline dump $(if $(OUT),--out "$(OUT)",)

##@ Agents

sync-agents: ## Regenerate agent pointers from .agents/
	uv run --no-project tooling/sync_agents.py

check-agents: ## Fail if agent pointers drifted from .agents/
	uv run --no-project tooling/sync_agents.py --check
