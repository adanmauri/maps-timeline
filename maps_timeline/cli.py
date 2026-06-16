"""Command-line interface (typer).

Examples:
    uv run maps-timeline scrape --days 3
    uv run maps-timeline normalize
    uv run maps-timeline run --days 3
    uv run maps-timeline parse-file dump_dia.xml      # offline test against a saved dump
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

app = typer.Typer(add_completion=False, help="Extractor for the Google Maps Timeline (Routes).")

_TIMELINE_SETUP_HINT = (
    "Open Google Maps → Rutas → Día on the day you want to start from. "
    "The scraper will swipe the activity sheet up if it is collapsed or half-open."
)


def _exit_on_missing_paths(exc: FileNotFoundError) -> NoReturn:
    """Print a friendly message and exit when default run paths are unavailable."""
    typer.echo(str(exc))
    raise typer.Exit(code=1) from None


@app.command()
def scrape(
    days: Annotated[
        int, typer.Option(help="Number of days to step back from the displayed day.")
    ] = 3,
    out: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Output folder for the JSONL. "
                "Defaults to a new timestamped folder under data/runs/."
            ),
        ),
    ] = None,
    serial: Annotated[
        str | None, typer.Option(help="Device serial (if more than one is connected).")
    ] = None,
    prefer: Annotated[str, typer.Option(help="Preferred driver: 'u2' or 'adb'.")] = "u2",
    on_error: Annotated[str, typer.Option(help="On navigation error: 'skip' or 'abort'.")] = "skip",
):
    """Walk the Timeline day by day and save each day as one JSONL line."""
    from .device import make_driver  # pylint: disable=import-outside-toplevel
    from .paths import resolve_scrape_out  # pylint: disable=import-outside-toplevel
    from .pipeline import scrape as run_scrape  # pylint: disable=import-outside-toplevel

    raw_out, run_dir = resolve_scrape_out(out)
    if run_dir is not None:
        typer.echo(f"Export run: {run_dir}")

    typer.echo(_TIMELINE_SETUP_HINT)
    driver = make_driver(serial=serial, prefer=prefer)
    result = run_scrape(driver, today=date.today(), n_days=days, out_dir=raw_out, on_error=on_error)
    typer.echo(
        f"\nDone: {result.days_scraped} days -> {result.output_path}"
        + (f" | failed: {result.days_failed}" if result.days_failed else "")
    )


@app.command()
def normalize(
    jsonl: Annotated[
        Path | None,
        typer.Option(
            help="Raw input JSONL. Defaults to the latest export run under data/runs/.",
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            help="Output folder (CSV + Parquet). Defaults to the matching run's clean/ folder.",
        ),
    ] = None,
    geocode: Annotated[
        bool,
        typer.Option(help="Add lat/lon by resolving addresses via Nominatim (OpenStreetMap)."),
    ] = False,
    nominatim_email: Annotated[
        str | None,
        typer.Option(
            help=(
                "Contact email included in Nominatim HTTP requests when --geocode is set. "
                "No signup required; Nominatim may use it to reach you about usage issues."
            ),
        ),
    ] = None,
):
    """Convert the raw JSONL into a clean dataset (CSV + Parquet)."""
    from .normalize import normalize as run_normalize  # pylint: disable=import-outside-toplevel
    from .paths import resolve_normalize_paths  # pylint: disable=import-outside-toplevel

    try:
        jsonl_path, clean_out = resolve_normalize_paths(jsonl, out)
    except FileNotFoundError as exc:
        _exit_on_missing_paths(exc)

    geocoder = None
    if geocode:
        from .geocode import NominatimGeocoder  # pylint: disable=import-outside-toplevel

        contact = nominatim_email or "anon@example.com"
        geocoder = NominatimGeocoder(
            cache_path=Path("data/cache/geocode.json"),
            user_agent=f"maps-timeline/0.1 ({contact})",
        )
    run_normalize(jsonl_path, clean_out, geocoder=geocoder)


@app.command()
def stats(
    source: Annotated[
        Path | None,
        typer.Option(
            help="Clean dataset to read (.parquet or .csv). Defaults to the latest export run.",
        ),
    ] = None,
    top: Annotated[int, typer.Option(help="How many of the most visited places to show.")] = 10,
):
    """Print a console summary of the exported dataset (distance, places, time)."""
    from .paths import resolve_stats_source  # pylint: disable=import-outside-toplevel
    from .stats import load_dataframe, render, summarize  # pylint: disable=import-outside-toplevel

    try:
        dataset = resolve_stats_source(source)
    except FileNotFoundError as exc:
        _exit_on_missing_paths(exc)

    if not dataset.exists() and dataset.suffix == ".parquet":
        dataset = dataset.with_suffix(".csv")
    try:
        df = load_dataframe(dataset)
    except FileNotFoundError:
        typer.echo(f"No dataset found at {dataset}. Run 'normalize' first.")
        raise typer.Exit(code=1) from None
    typer.echo(render(summarize(df, top=top)))


@app.command()
def run(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    days: Annotated[
        int, typer.Option(help="Number of days to step back from the displayed day.")
    ] = 3,
    raw_out: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Output folder for the raw JSONL. "
                "With --clean-out omitted, defaults to a new data/runs/<timestamp>/ folder."
            ),
        ),
    ] = None,
    clean_out: Annotated[
        Path | None,
        typer.Option(
            help="Output folder for CSV + Parquet. Defaults to the same versioned run as raw.",
        ),
    ] = None,
    serial: Annotated[
        str | None, typer.Option(help="Device serial (if more than one is connected).")
    ] = None,
    prefer: Annotated[str, typer.Option(help="Preferred driver: 'u2' or 'adb'.")] = "u2",
    on_error: Annotated[str, typer.Option(help="On navigation error: 'skip' or 'abort'.")] = "skip",
    geocode: Annotated[
        bool,
        typer.Option(help="Add lat/lon by resolving addresses via Nominatim (OpenStreetMap)."),
    ] = False,
    nominatim_email: Annotated[
        str | None,
        typer.Option(
            help=(
                "Contact email included in Nominatim HTTP requests when --geocode is set. "
                "No signup required; Nominatim may use it to reach you about usage issues."
            ),
        ),
    ] = None,
    top: Annotated[int, typer.Option(help="How many of the most visited places to show.")] = 10,
):
    """Scrape the Timeline, normalize to CSV/Parquet, and print a summary."""
    from .device import make_driver  # pylint: disable=import-outside-toplevel
    from .normalize import normalize as run_normalize  # pylint: disable=import-outside-toplevel
    from .paths import (  # pylint: disable=import-outside-toplevel
        clean_dir_for_jsonl,
        resolve_scrape_out,
    )
    from .pipeline import scrape as run_scrape  # pylint: disable=import-outside-toplevel
    from .stats import load_dataframe, render, summarize  # pylint: disable=import-outside-toplevel

    raw_dir, run_dir = resolve_scrape_out(raw_out)
    if run_dir is not None:
        typer.echo(f"Export run: {run_dir}")
        normalize_out = run_dir / "clean"
    elif clean_out is not None:
        normalize_out = clean_out
    else:
        normalize_out = Path("data/clean")

    typer.echo("[1/3] Scraping Timeline...")
    typer.echo(_TIMELINE_SETUP_HINT)
    driver = make_driver(serial=serial, prefer=prefer)
    result = run_scrape(driver, today=date.today(), n_days=days, out_dir=raw_dir, on_error=on_error)
    typer.echo(
        f"Scraped {result.days_scraped} days -> {result.output_path}"
        + (f" | failed: {result.days_failed}" if result.days_failed else "")
    )

    if clean_out is None and run_dir is None:
        normalize_out = clean_dir_for_jsonl(result.output_path)

    geocoder = None
    if geocode:
        from .geocode import NominatimGeocoder  # pylint: disable=import-outside-toplevel

        contact = nominatim_email or "anon@example.com"
        geocoder = NominatimGeocoder(
            cache_path=Path("data/cache/geocode.json"),
            user_agent=f"maps-timeline/0.1 ({contact})",
        )

    typer.echo("\n[2/3] Normalizing dataset...")
    csv_path = run_normalize(result.output_path, normalize_out, geocoder=geocoder)

    typer.echo("\n[3/3] Summary:")
    stats_source = csv_path.with_suffix(".parquet")
    if not stats_source.exists():
        stats_source = csv_path
    df = load_dataframe(stats_source)
    typer.echo(render(summarize(df, top=top)))


@app.command("parse-file")
def parse_file(
    path: Annotated[Path, typer.Argument(help="Path to a saved XML dump.")],
    day: Annotated[
        str | None, typer.Option(help="Dump date (YYYY-MM-DD); defaults to reading the header.")
    ] = None,
):
    """Parse a local XML dump and print the result (offline test, no phone)."""
    from .navigator import resolve_header_date  # pylint: disable=import-outside-toplevel
    from .parser import parse_day  # pylint: disable=import-outside-toplevel

    xml = path.read_text(encoding="utf-8")
    header = read_header_text_safe(xml)
    the_day = (
        date.fromisoformat(day)
        if day
        else (resolve_header_date(header, date.today()) if header else date.today())
    )
    timeline = parse_day(xml, the_day)
    typer.echo(timeline.model_dump_json(indent=2))
    typer.echo(
        f"\n{len(timeline.segments)} segments | {timeline.place_visits} visits "
        f"| matches summary: {timeline.summary_matches()}"
    )


def read_header_text_safe(xml: str) -> str | None:
    """Parse `xml` and return the Timeline header text, or None on failure."""
    import xml.etree.ElementTree as ET  # nosec B405  # pylint: disable=import-outside-toplevel

    from .parser import read_header_text  # pylint: disable=import-outside-toplevel

    return read_header_text(ET.fromstring(xml))  # nosec B314


@app.command()
def dump(
    out: Annotated[Path, typer.Option(help="Where to save the dump.")] = Path("dump.xml"),
    serial: Annotated[str | None, typer.Option(help="Device serial.")] = None,
    prefer: Annotated[str, typer.Option(help="Preferred driver: 'u2' or 'adb'.")] = "u2",
):
    """Take a single dump of the current screen and save it (to calibrate selectors)."""
    from .device import make_driver  # pylint: disable=import-outside-toplevel

    driver = make_driver(serial=serial, prefer=prefer)
    out.write_text(driver.dump(), encoding="utf-8")
    typer.echo(f"Dump saved to {out}")


def main() -> None:
    """Console entry point when the module is executed as a script."""
    app()
