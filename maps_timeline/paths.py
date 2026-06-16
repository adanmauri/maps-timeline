"""Versioned run directories under data/runs (sensitive data stays gitignored)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

RUNS_DIR = Path("data/runs")
LATEST_MARKER = Path("data/latest")
RAW_JSONL = "timeline.jsonl"
CLEAN_PARQUET = "timeline.parquet"
CLEAN_CSV = "timeline.csv"


def run_stamp(when: datetime | None = None) -> str:
    """Return a filesystem-safe directory name for one export run."""
    moment = when or datetime.now()
    return moment.strftime("%Y-%m-%d_%H%M%S")


def create_run_dir(*, runs_root: Path | None = None, when: datetime | None = None) -> Path:
    """Create a new timestamped run folder with raw/ and clean/ subdirectories."""
    root = runs_root or RUNS_DIR
    run_dir = root / run_stamp(when)
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    (run_dir / "clean").mkdir(parents=True, exist_ok=True)
    write_latest_marker(run_dir)
    return run_dir


def write_latest_marker(run_dir: Path, *, marker: Path | None = None) -> None:
    """Record `run_dir` as the most recent export run."""
    latest = marker or LATEST_MARKER
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(str(run_dir.resolve()) + "\n", encoding="utf-8")


def read_latest_run_dir(*, marker: Path | None = None) -> Path | None:
    """Return the latest run directory, or None when no marker exists."""
    latest = marker or LATEST_MARKER
    if not latest.is_file():
        return None
    run_dir = Path(latest.read_text(encoding="utf-8").strip())
    return run_dir if run_dir.is_dir() else None


def resolve_scrape_out(out: Path | None) -> tuple[Path, Path | None]:
    """Return `(raw_out_dir, run_dir)`; create a versioned run when `out` is None."""
    if out is not None:
        return out, None
    run_dir = create_run_dir()
    return run_dir / "raw", run_dir


def clean_dir_for_jsonl(jsonl: Path) -> Path:
    """Infer the clean output folder from a JSONL path inside a versioned run."""
    if jsonl.parent.name == "raw" and jsonl.parent.parent.name != "raw":
        return jsonl.parent.parent / "clean"
    return Path("data/clean")


def resolve_normalize_paths(
    jsonl: Path | None,
    out: Path | None,
) -> tuple[Path, Path]:
    """Resolve raw JSONL input and clean output paths from CLI defaults."""
    if jsonl is None:
        run_dir = read_latest_run_dir()
        if run_dir is None:
            msg = "No export runs found. Run 'scrape' or 'run' first, or pass --jsonl."
            raise FileNotFoundError(msg)
        jsonl = run_dir / "raw" / RAW_JSONL
    if not jsonl.is_file():
        msg = f"No raw JSONL at {jsonl}. Run 'scrape' or 'run' first, or pass --jsonl."
        raise FileNotFoundError(msg)
    clean_out = out if out is not None else clean_dir_for_jsonl(jsonl)
    return jsonl, clean_out


def resolve_stats_source(source: Path | None) -> Path:
    """Resolve the clean dataset path from CLI defaults."""
    if source is not None:
        return source
    run_dir = read_latest_run_dir()
    if run_dir is None:
        msg = "No export runs found. Run 'normalize' or 'run' first, or pass --source."
        raise FileNotFoundError(msg)
    return run_dir / "clean" / CLEAN_PARQUET
