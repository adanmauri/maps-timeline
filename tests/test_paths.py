"""Tests for versioned export run paths."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from maps_timeline.paths import (
    clean_dir_for_jsonl,
    create_run_dir,
    read_latest_run_dir,
    resolve_normalize_paths,
    resolve_scrape_out,
    resolve_stats_source,
    run_stamp,
    write_latest_marker,
)


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


def test_resolve_normalize_paths_from_latest(isolated_paths):
    """Default normalize input/output come from the latest run."""
    runs_root, marker = isolated_paths
    run_dir = runs_root / "2026-06-10_120000"
    jsonl = run_dir / "raw" / "timeline.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text("{}\n", encoding="utf-8")
    write_latest_marker(run_dir, marker=marker)

    resolved_jsonl, clean = resolve_normalize_paths(None, None)

    assert resolved_jsonl == jsonl
    assert clean == run_dir / "clean"


def test_resolve_normalize_paths_without_latest(isolated_paths):
    """Fail clearly when no export runs exist yet."""
    _runs_root, _marker = isolated_paths
    with pytest.raises(FileNotFoundError, match="No export runs found"):
        resolve_normalize_paths(None, None)


def test_resolve_normalize_paths_missing_jsonl(isolated_paths):
    """Fail clearly when the latest run has no raw JSONL yet."""
    runs_root, marker = isolated_paths
    run_dir = runs_root / "2026-06-10_120000"
    (run_dir / "raw").mkdir(parents=True)
    write_latest_marker(run_dir, marker=marker)
    with pytest.raises(FileNotFoundError, match="No raw JSONL"):
        resolve_normalize_paths(None, None)


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
