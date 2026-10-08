"""Tests for versioned export run paths."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from maps_timeline.paths import (
    attach_export,
    clean_dir_for_jsonl,
    create_run_dir,
    earlier_scrapes,
    read_latest_run_dir,
    resolve_normalize_sources,
    resolve_scrape_out,
    resolve_stats_source,
    run_date,
    run_stamp,
    write_latest_marker,
)
from tests.conftest import write_run_scrape


def test_run_stamp_is_filesystem_safe():
    """Format timestamps as YYYY-MM-DD_HHMMSS."""
    assert run_stamp(datetime(2026, 6, 10, 15, 30, 45)) == "2026-06-10_153045"


def test_create_run_dir_layout(isolated_paths):
    """Create raw/ and clean/ under a timestamped run folder."""
    runs_root, _marker = isolated_paths
    run_dir = create_run_dir(runs_root=runs_root, when=datetime(2026, 6, 10, 12, 0, 0))
    assert run_dir == runs_root / "2026-06-10_120000"
    assert (run_dir / "raw").is_dir()
    assert (run_dir / "clean").is_dir()


def test_latest_marker_roundtrip(isolated_paths):
    """Persist and read back the most recent run directory."""
    runs_root, marker = isolated_paths
    run_dir = runs_root / "2026-06-10_120000"
    run_dir.mkdir(parents=True)
    write_latest_marker(run_dir, marker=marker)
    assert read_latest_run_dir(marker=marker) == run_dir


def test_read_latest_run_dir_ignores_stale_marker(isolated_paths):
    """Return None when the marker points at a directory that no longer exists."""
    _runs_root, marker = isolated_paths
    marker.write_text("/tmp/deleted-run\n", encoding="utf-8")
    assert read_latest_run_dir(marker=marker) is None


def test_resolve_scrape_out_creates_versioned_run(isolated_paths):
    """Default scrape output creates a new run directory."""
    _runs_root, marker = isolated_paths
    raw_out, run_dir = resolve_scrape_out(None)
    assert run_dir is not None
    assert raw_out == run_dir / "raw"
    assert read_latest_run_dir(marker=marker) == run_dir


def test_resolve_scrape_out_honors_explicit_path(tmp_path: Path):
    """Keep legacy behavior when the caller passes an explicit output folder."""
    explicit = tmp_path / "raw"
    raw_out, run_dir = resolve_scrape_out(explicit)
    assert raw_out == explicit
    assert run_dir is None


def test_clean_dir_for_jsonl_inside_run(tmp_path: Path):
    """Infer clean/ from a JSONL path inside a versioned run."""
    jsonl = tmp_path / "runs" / "2026-06-10_120000" / "raw" / "timeline.jsonl"
    assert clean_dir_for_jsonl(jsonl) == tmp_path / "runs" / "2026-06-10_120000" / "clean"


def test_clean_dir_for_jsonl_legacy_flat_layout():
    """Map the legacy data/raw layout to data/clean."""
    jsonl = Path("data/raw/timeline.jsonl")
    assert clean_dir_for_jsonl(jsonl) == Path("data/clean")


def test_clean_dir_for_jsonl_non_raw_parent(tmp_path: Path):
    """Fall back to data/clean when the JSONL is not under a raw/ folder."""
    jsonl = tmp_path / "timeline.jsonl"
    assert clean_dir_for_jsonl(jsonl) == Path("data/clean")


def _latest_run(isolated_paths, *files: str) -> Path:
    """Create the latest run with the given raw/ files and return its folder."""
    runs_root, marker = isolated_paths
    run_dir = runs_root / "2026-06-10_120000"
    (run_dir / "raw").mkdir(parents=True)
    for name in files:
        (run_dir / "raw" / name).write_text("{}\n", encoding="utf-8")
    write_latest_marker(run_dir, marker=marker)
    return run_dir


def test_resolve_normalize_sources_from_latest(isolated_paths):
    """Default normalize input/output come from the latest run."""
    run_dir = _latest_run(isolated_paths, "timeline.jsonl")

    jsonl, export, clean = resolve_normalize_sources(None, None, None)

    assert jsonl == run_dir / "raw" / "timeline.jsonl"
    assert export is None
    assert clean == run_dir / "clean"


def test_resolve_normalize_sources_picks_up_export(isolated_paths):
    """An official export next to the JSONL is merged automatically."""
    run_dir = _latest_run(isolated_paths, "timeline.jsonl", "export.json")

    jsonl, export, _clean = resolve_normalize_sources(None, None, None)

    assert jsonl == run_dir / "raw" / "timeline.jsonl"
    assert export == run_dir / "raw" / "export.json"


def test_resolve_normalize_sources_export_only_run(isolated_paths):
    """A run created by 'import' has only the official export."""
    run_dir = _latest_run(isolated_paths, "export.json")

    jsonl, export, clean = resolve_normalize_sources(None, None, None)

    assert jsonl is None
    assert export == run_dir / "raw" / "export.json"
    assert clean == run_dir / "clean"


def test_resolve_normalize_sources_without_latest(isolated_paths):
    """Fail clearly when no export runs exist yet."""
    _runs_root, _marker = isolated_paths
    with pytest.raises(FileNotFoundError, match="No export runs found"):
        resolve_normalize_sources(None, None, None)


def test_resolve_normalize_sources_empty_run(isolated_paths):
    """Fail clearly when the latest run has no raw data yet."""
    _latest_run(isolated_paths)
    with pytest.raises(FileNotFoundError, match="No raw JSONL or official export"):
        resolve_normalize_sources(None, None, None)


def test_resolve_normalize_sources_missing_explicit_files(tmp_path: Path):
    """Fail clearly when an explicit input does not exist."""
    with pytest.raises(FileNotFoundError, match="No raw JSONL at"):
        resolve_normalize_sources(tmp_path / "missing.jsonl", None, None)
    with pytest.raises(FileNotFoundError, match="No official Timeline export"):
        resolve_normalize_sources(None, tmp_path / "missing.json", None)


def test_resolve_normalize_sources_explicit_export(tmp_path: Path):
    """An explicit export alone is normalized on its own."""
    export = tmp_path / "Timeline.json"
    export.write_text("{}", encoding="utf-8")
    out = tmp_path / "out"

    assert resolve_normalize_sources(None, export, out) == (None, export, out)
    assert resolve_normalize_sources(None, export, None)[2] == Path("data/clean")


def test_attach_export_copies_into_raw(tmp_path: Path):
    """Copy the export verbatim into raw/export.json, tolerating re-attaching the copy."""
    source = tmp_path / "Timeline.json"
    source.write_text('{"semanticSegments": []}', encoding="utf-8")
    raw_dir = tmp_path / "run" / "raw"

    target = attach_export(source, raw_dir)

    assert target == raw_dir / "export.json"
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert attach_export(target, raw_dir) == target


def test_run_date_from_stamp():
    """Read the creation day from a run folder name; None for other folders."""
    assert run_date(Path("data/runs/2026-06-10_153045")) == date(2026, 6, 10)
    assert run_date(Path("data/clean")) is None


def test_earlier_scrapes_oldest_first_without_current(isolated_paths):
    """List every run's raw JSONL in run order, leaving out the current one."""
    runs_root, _marker = isolated_paths
    newer = write_run_scrape(runs_root, "2026-06-10_090000")
    older = write_run_scrape(runs_root, "2026-06-08_100000")
    (runs_root / "2026-06-09_100000" / "raw").mkdir(parents=True)  # export-only run
    assert earlier_scrapes() == [older, newer]
    assert earlier_scrapes(newer) == [older]


def test_resolve_stats_source_from_latest(isolated_paths):
    """Default stats input comes from the latest run parquet file."""
    runs_root, marker = isolated_paths
    run_dir = runs_root / "2026-06-10_120000"
    (run_dir / "clean").mkdir(parents=True)
    write_latest_marker(run_dir, marker=marker)

    source = resolve_stats_source(None)

    assert source == run_dir / "clean" / "timeline.parquet"


def test_resolve_stats_source_without_latest(isolated_paths):
    """Fail clearly when no export runs exist yet."""
    _runs_root, _marker = isolated_paths
    with pytest.raises(FileNotFoundError, match="No export runs found"):
        resolve_stats_source(None)
