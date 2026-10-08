"""Versioned run directories under data/runs (sensitive data stays gitignored)."""

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

RUNS_DIR = Path("data/runs")
LATEST_MARKER = Path("data/latest")
RAW_JSONL = "timeline.jsonl"
RAW_EXPORT = "export.json"  # official on-device Timeline export, copied verbatim
PLACE_NAMES_CACHE = Path("data/cache/places.json")  # place ID -> name learned from scrapes
CLEAN_PARQUET = "timeline.parquet"
CLEAN_CSV = "timeline.csv"
STAMP_FORMAT = "%Y-%m-%d_%H%M%S"


def run_stamp(when: datetime | None = None) -> str:
    """Return a filesystem-safe directory name for one export run."""
    moment = when or datetime.now()
    return moment.strftime(STAMP_FORMAT)


def run_date(run_dir: Path) -> date | None:
    """Return the day a versioned run was created, from its folder name (None otherwise)."""
    try:
        return datetime.strptime(run_dir.name, STAMP_FORMAT).date()
    except ValueError:
        return None


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


def earlier_scrapes(current: Path | None = None) -> list[Path]:
    """Return the raw JSONL of every run under data/runs/, oldest first, except `current`."""
    skip = current.resolve() if current is not None else None
    return [path for path in sorted(RUNS_DIR.glob(f"*/raw/{RAW_JSONL}")) if path.resolve() != skip]


def attach_export(source: Path, raw_dir: Path) -> Path:
    """Copy an official Timeline export into a run's raw/ folder and return the copy."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / RAW_EXPORT
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target


def resolve_normalize_sources(
    jsonl: Path | None,
    export: Path | None,
    out: Path | None,
) -> tuple[Path | None, Path | None, Path]:
    """Resolve the raw JSONL and/or official export plus the clean output folder.

    Without explicit inputs, both come from the latest run's raw/ folder. An official
    export sitting next to the JSONL (raw/export.json) is picked up automatically.
    """
    raw_dir: Path | None = None
    if jsonl is None and export is None:
        run_dir = read_latest_run_dir()
        if run_dir is None:
            msg = "No export runs found. Run 'scrape', 'run' or 'import' first, or pass --jsonl."
            raise FileNotFoundError(msg)
        raw_dir = run_dir / "raw"
        candidate = raw_dir / RAW_JSONL
        jsonl = candidate if candidate.is_file() else None
    if jsonl is not None:
        if not jsonl.is_file():
            msg = f"No raw JSONL at {jsonl}. Run 'scrape' or 'run' first, or pass --jsonl."
            raise FileNotFoundError(msg)
        raw_dir = jsonl.parent
    if export is None and raw_dir is not None:
        sibling = raw_dir / RAW_EXPORT
        export = sibling if sibling.is_file() else None
    if export is not None and not export.is_file():
        msg = f"No official Timeline export at {export}. Check the path passed to --export."
        raise FileNotFoundError(msg)
    source = jsonl if jsonl is not None else export
    if source is None:
        msg = (
            f"No raw JSONL or official export in {raw_dir}. "
            "Run 'scrape', 'run' or 'import' first, or pass --jsonl / --export."
        )
        raise FileNotFoundError(msg)
    clean_out = out if out is not None else clean_dir_for_jsonl(source)
    return jsonl, export, clean_out


def resolve_stats_source(source: Path | None) -> Path:
    """Resolve the clean dataset path from CLI defaults."""
    if source is not None:
        return source
    run_dir = read_latest_run_dir()
    if run_dir is None:
        msg = "No export runs found. Run 'normalize' or 'run' first, or pass --source."
        raise FileNotFoundError(msg)
    return run_dir / "clean" / CLEAN_PARQUET
