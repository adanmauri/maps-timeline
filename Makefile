# maps-timeline - Makefile
# CLI tool that extracts the Google Maps Timeline (Rutas) over ADB.
# Targets wrap UV + the project tooling.

# Quality/test target directory. Override with DIR=path or as the second goal
# (e.g. `make lint maps_timeline`). Defaults to the source and tests directories.
_qual_dir := $(or $(DIR),$(word 2,$(MAKECMDGOALS)),maps_timeline tests)

# Package name and CLI entry point.
PKG := maps_timeline
CLI := maps-timeline

# Green OK / cyan section titles.
define ECHO_OK
	@printf '\033[32m%s\033[0m\n' "$(1)"
endef
define ECHO_TITLE
	@printf '\033[36m%s\033[0m\n' "$(1)"
endef

.PHONY: help install install-dev clean clean-cache clean-deps \
	run scrape normalize parse-file dump \
	test test-coverage \
	lint type-check security quality format format-quality \
	maps_timeline tests

# Default target
help:
	@echo ""
	$(call ECHO_TITLE,maps-timeline - Development Commands)
	@echo "======================================"
	@echo ""
	$(call ECHO_TITLE,[ENV] Environment & Dependencies:)
	@echo "  install                 - Install production dependencies only"
	@echo "  install-dev             - Install all dependencies (incl. dev) + pre-commit hooks"
	@echo "  clean-cache             - Remove build artifacts and caches (keeps .venv)"
	@echo "  clean-deps              - Remove .venv and clear uv cache"
	@echo "  clean                   - clean-cache + clean-deps"
	@echo ""
	$(call ECHO_TITLE,[RUN] CLI:)
	@echo "  run                     - Run the CLI. ARGS=\"...\" (e.g. ARGS=\"--help\")"
	@echo "  scrape                  - Scrape the Timeline. ARGS=\"--days 3\""
	@echo "  normalize               - Normalize raw JSONL to CSV + Parquet. ARGS=\"--geocode\""
	@echo "  parse-file              - Offline parse of a saved dump. FILE=dump_dia.xml"
	@echo "  dump                    - Dump the current screen. OUT=dump.xml"
	@echo ""
	$(call ECHO_TITLE,[TEST] Testing:)
	@echo "  test                    - Run the test suite (pytest)"
	@echo "  test-coverage           - Run tests with coverage (term + HTML report)"
	@echo ""
	@echo "  Usage:          make test ARGS=\"...\" for pytest"
	@echo ""
	$(call ECHO_TITLE,[QUALITY] Code Quality:)
	@echo "  lint                    - ruff, flake8, pylint"
	@echo "  type-check              - mypy, pyright"
	@echo "  security                - bandit (+ trivy if installed)"
	@echo "  quality                 - lint + type-check + security"
	@echo "  format                  - black, isort, ruff --fix"
	@echo "  format-quality          - format then quality"
	@echo ""
	@echo "  Usage:          make <target> [path] or DIR=path (default: maps_timeline tests)"
	@echo "  Examples:       make lint maps_timeline   make type-check tests"
	@echo ""

# --- Environment & dependencies ---

# Install production dependencies only.
install:
	@echo "INFO: Installing production dependencies with UV..."
	@uv sync --no-group dev || (echo "ERROR: Failed to install dependencies" && exit 1)
	$(call ECHO_OK,OK: Installation complete.)

# Install all dependencies (production + development) and set up pre-commit hooks.
install-dev:
	@echo "INFO: Installing all dependencies (production + development) with UV..."
	@uv sync --group dev || (echo "ERROR: Failed to install development dependencies" && exit 1)
	@echo "INFO: Installing pre-commit hooks (commit + pre-push)..."
	@uv run pre-commit install
	@uv run pre-commit install --hook-type pre-push
	$(call ECHO_OK,OK: Installation complete.)

# Remove build artifacts and caches (does not remove .venv).
clean-cache:
	@echo "INFO: Removing build artifacts and caches..."
	@find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml dist build
	$(call ECHO_OK,OK: Build artifacts and caches removed.)

# Remove .venv and clear the uv cache.
clean-deps:
	@echo "INFO: Removing .venv and clearing uv cache..."
	@rm -rf .venv
	@-uv cache clean
	$(call ECHO_OK,OK: Dependencies cleaned.)

# clean-cache + clean-deps; leaves the environment at zero. Run make install-dev afterwards.
clean: clean-cache clean-deps
	$(call ECHO_OK,OK: Environment at zero. Run make install-dev to reinstall.)

# --- CLI ---

# Run the CLI with arbitrary arguments. Usage: make run ARGS="scrape --days 3"
run:
	@uv run $(CLI) $(ARGS)

# Scrape the Timeline. Usage: make scrape ARGS="--days 3"
scrape:
	@echo "INFO: Open Google Maps on the Timeline ('Day' view) before running."
	@uv run $(CLI) scrape $(ARGS)

# Normalize the raw JSONL into CSV + Parquet. Usage: make normalize ARGS="--geocode --nominatim-email you@example.com"
normalize:
	@uv run $(CLI) normalize $(ARGS)

# Offline parse of a saved dump. Usage: make parse-file FILE=dump_dia.xml
parse-file:
	@test -n "$(FILE)" || (echo "ERROR: FILE is required, e.g. make parse-file FILE=dump_dia.xml" && exit 1)
	@uv run $(CLI) parse-file $(FILE)

# Dump the current screen to a file. Usage: make dump OUT=dump.xml
dump:
	@uv run $(CLI) dump $(if $(OUT),--out $(OUT),)

# --- Testing ---

_pytest_cov_opts = --cov=$(PKG) --cov-report=html --cov-report=term-missing
_test_goals := test test-coverage

# Run the test suite. Usage: make test ARGS="-k parser"
test:
	@echo "INFO: Running tests..."
	@uv run pytest $(or $(ARGS),$(filter-out $(_test_goals),$(MAKECMDGOALS))) || (echo "ERROR: Tests failed" && exit 1)
	$(call ECHO_OK,OK: All tests passed.)

# Run tests with coverage (terminal + HTML report under htmlcov/).
test-coverage:
	@echo "INFO: Running tests with coverage..."
	@uv run pytest $(_pytest_cov_opts) $(or $(ARGS),$(filter-out $(_test_goals),$(MAKECMDGOALS))) || (echo "ERROR: Tests failed" && exit 1)
	$(call ECHO_OK,OK: All tests passed.)

# --- Code quality ---

# Lint: style, conventions, potential bugs. Usage: make lint [path] or DIR=path
lint:
	@echo "INFO: Running linters (ruff, flake8, pylint)..."
	@uv run ruff check $(_qual_dir) || (echo "ERROR: Ruff check failed" && exit 1)
	@uv run flake8 $(_qual_dir) || (echo "ERROR: Flake8 check failed" && exit 1)
	@uv run pylint $(_qual_dir) || (echo "ERROR: Pylint check failed" && exit 1)
	$(call ECHO_OK,OK: Lint passed.)

# Type-check: static type checking (mypy, pyright).
type-check:
	@echo "INFO: Running type checking (mypy, pyright)..."
	@uv run mypy $(_qual_dir) || (echo "ERROR: mypy failed" && exit 1)
	@uv run pyright $(_qual_dir) || (echo "ERROR: pyright failed" && exit 1)
	$(call ECHO_OK,OK: Type checking passed.)

# Security: bandit (always) + trivy (if on PATH).
security:
	@uv run python -c "import shutil; print('INFO: Running security scan (bandit, trivy)...' if shutil.which('trivy') else 'INFO: Running security scan (bandit). Trivy not installed, skipping.')"
	@uv run bandit -r maps_timeline || (echo "ERROR: Bandit failed" && exit 1)
	@uv run python -c "import shutil,subprocess,sys; e=shutil.which('trivy'); sys.exit(subprocess.call([e,'fs','.']) if e else 0)"
	$(call ECHO_OK,OK: Security scan passed.)

# Unified: lint + type-check + security.
quality: lint type-check security
	$(call ECHO_OK,OK: Quality passed.)

# Format (apply fixes): black, isort, ruff --fix.
format:
	@echo "INFO: Applying format fixes (black, isort, ruff --fix)..."
	@uv run black $(_qual_dir) || (echo "ERROR: Black failed" && exit 1)
	@uv run isort $(_qual_dir) || (echo "ERROR: Isort failed" && exit 1)
	@uv run ruff check --fix $(_qual_dir) || (echo "ERROR: Ruff check --fix failed" && exit 1)
	$(call ECHO_OK,OK: Format applied.)

# Run format then quality.
format-quality: format quality
	$(call ECHO_OK,OK: Format and quality passed.)

# Catch-all so a second goal used as a path (e.g. `make lint maps_timeline`) is not built as a target.
.SILENT: maps_timeline tests . docs
%:
	@:
