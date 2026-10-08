"""Command-line interface (typer).

Examples:
    uv run maps-timeline scrape --days 3
    uv run maps-timeline normalize
    uv run maps-timeline run --days 3
    uv run maps-timeline import Timeline.json         # official on-device export
    uv run maps-timeline run --export Timeline.json   # the export plans which days to capture
    uv run maps-timeline parse-file dump_dia.xml      # offline test against a saved dump
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

if TYPE_CHECKING:
    from .geocode import NominatimGeocoder
    from .pipeline import ScrapeResult
    from .planner import ScrapePlan

app = typer.Typer(add_completion=False, help="Extractor for the Google Maps Timeline (Routes).")

_TIMELINE_SETUP_HINT = (
    "Open Google Maps → Rutas → Día on the day you want to start from. "
    "The scraper will swipe the activity sheet up if it is collapsed or half-open."
)


def _exit_with_message(exc: FileNotFoundError | ValueError) -> NoReturn:
    """Print a friendly message and exit when inputs are missing or cannot be read."""
    typer.echo(str(exc))
    raise typer.Exit(code=1) from None


def _make_geocoder(geocode: bool, nominatim_email: str | None) -> NominatimGeocoder | None:
    """Return a cached Nominatim geocoder when --geocode is set, else None."""
    if not geocode:
        return None
    from .geocode import (  # pylint: disable=import-outside-toplevel,redefined-outer-name
        NominatimGeocoder,
    )

    contact = nominatim_email or "anon@example.com"
    return NominatimGeocoder(
        cache_path=Path("data/cache/geocode.json"),
        user_agent=f"maps-timeline/0.1 ({contact})",
    )


_DAYS_HELP = (
    "Number of days to step back from the displayed day. Default: 3, or planned from --export."
)
_SINCE_HELP = (
    "With --export and no --days: only look for places visited on or after this day "
    "(YYYY-MM-DD), to walk back less. Default: no limit."
)
_UNTIL_HELP = (
    "With --export and no --days: only plan days on or before this day (YYYY-MM-DD). "
    "The walk still starts from the day shown in Maps; newer days are only stepped over. "
    "Default: today."
)


def _date_window(
    since: datetime | None, until: datetime | None, today: date
) -> tuple[date | None, date]:
    """Return the planning window from --since / --until (until capped at today)."""
    first = since.date() if since is not None else None
    last = until.date() if until is not None else today
    if first is not None and first > last:
        _exit_with_message(ValueError(f"--since {first} is after --until {last}: nothing to plan."))
    return first, min(last, today)


def _prepare_export(
    export: Path | None, days: int | None, window: tuple[date | None, date], today: date
) -> ScrapePlan | None:
    """Validate the official export and, when --days is omitted, plan the days to capture.

    The plan skips places already named (cache and every earlier run's scrape) and days
    earlier runs captured completely; `window` is the (since, until) range to plan in.
    """
    if export is None:
        return None
    from .merge import learned_so_far  # pylint: disable=import-outside-toplevel
    from .official import load_official_export  # pylint: disable=import-outside-toplevel
    from .paths import PLACE_NAMES_CACHE, earlier_scrapes  # pylint: disable=import-outside-toplevel
    from .planner import plan_scrape  # pylint: disable=import-outside-toplevel

    try:
        segments = load_official_export(export)  # fail fast, before a long scrape
    except ValueError as exc:
        _exit_with_message(exc)
    if days is not None:
        return None
    known, captured = learned_so_far(segments, earlier_scrapes(), PLACE_NAMES_CACHE)
    # Plan as if the walk started on --until; it is still measured from today.
    plan = plan_scrape(segments, window[1], known, since=window[0], captured=captured)
    typer.echo(plan.describe(today))
    if plan.oldest is None:
        raise typer.Exit(code=0)
    return plan


def _plan_walk(
    export: Path | None,
    days: int | None,
    since: datetime | None,
    until: datetime | None,
    today: date,
) -> tuple[int, ScrapePlan | None]:
    """Return how many days to walk and, with --export and no --days, the plan to follow."""
    plan = _prepare_export(export, days, _date_window(since, until, today), today)
    if plan is not None:
        return plan.walk_days(today), plan
    return (days if days is not None else 3), None


def _continue_hint(result: ScrapeResult, plan: ScrapePlan | None) -> None:
    """Tell how to resume when a planned walk stopped early."""
    if result.stopped is not None and plan is not None:
        typer.echo(
            "[·] Run the same command again to continue: "
            "days already captured are not planned again."
        )


@app.command()
def scrape(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    days: Annotated[int | None, typer.Option(help=_DAYS_HELP)] = None,
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
    export: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Official Timeline export (Timeline.json) to copy into the run, for "
                "'normalize' to merge. Without --days, it also decides which days to capture."
            ),
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    since: Annotated[datetime | None, typer.Option(help=_SINCE_HELP, formats=["%Y-%m-%d"])] = None,
    until: Annotated[datetime | None, typer.Option(help=_UNTIL_HELP, formats=["%Y-%m-%d"])] = None,
):
    """Walk the Timeline day by day and save each day as one JSONL line."""
    from .device import make_driver  # pylint: disable=import-outside-toplevel
    from .paths import attach_export, resolve_scrape_out  # pylint: disable=import-outside-toplevel
    from .pipeline import scrape as run_scrape  # pylint: disable=import-outside-toplevel

    today = date.today()
    n_days, plan = _plan_walk(export, days, since, until, today)
    driver = make_driver(serial=serial, prefer=prefer)  # before creating a run that stays empty
    raw_out, run_dir = resolve_scrape_out(out)
    if run_dir is not None:
        typer.echo(f"Export run: {run_dir}")

    typer.echo(_TIMELINE_SETUP_HINT)
    result = run_scrape(
        driver,
        today=today,
        n_days=n_days,
        out_dir=raw_out,
        on_error=on_error,
        only_days=plan.days if plan is not None else None,
    )
    if export is not None:
        attach_export(export, raw_out)
    typer.echo(
        f"\nDone: {result.days_scraped} days"
        + (f" (walked {result.days_walked})" if plan is not None else "")
        + f" -> {result.output_path}"
        + (f" | failed: {result.days_failed}" if result.days_failed else "")
    )
    _continue_hint(result, plan)


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
    export: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Official Timeline export (Timeline.json) to merge. "
                "Defaults to raw/export.json next to the JSONL, when present."
            ),
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
    """Convert the raw JSONL and/or official export into a clean dataset (CSV + Parquet)."""
    from .merge import build_dataset  # pylint: disable=import-outside-toplevel
    from .paths import (  # pylint: disable=import-outside-toplevel
        PLACE_NAMES_CACHE,
        earlier_scrapes,
        resolve_normalize_sources,
    )

    try:
        jsonl_path, export_path, clean_out = resolve_normalize_sources(jsonl, export, out)
    except FileNotFoundError as exc:
        _exit_with_message(exc)

    geocoder = _make_geocoder(geocode, nominatim_email)
    try:
        build_dataset(
            jsonl_path,
            export_path,
            clean_out,
            geocoder=geocoder,
            names_cache=PLACE_NAMES_CACHE,
            earlier=earlier_scrapes(jsonl_path),
        )
    except ValueError as exc:
        _exit_with_message(exc)


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
        _exit_with_message(exc)

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
    days: Annotated[int | None, typer.Option(help=_DAYS_HELP)] = None,
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
    export: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Official Timeline export (Timeline.json) to copy into the run and merge. "
                "Without --days, it also decides which days to capture."
            ),
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    since: Annotated[datetime | None, typer.Option(help=_SINCE_HELP, formats=["%Y-%m-%d"])] = None,
    until: Annotated[datetime | None, typer.Option(help=_UNTIL_HELP, formats=["%Y-%m-%d"])] = None,
):
    """Scrape the Timeline, normalize to CSV/Parquet, and print a summary."""
    from .device import make_driver  # pylint: disable=import-outside-toplevel
    from .merge import build_dataset  # pylint: disable=import-outside-toplevel
    from .paths import (  # pylint: disable=import-outside-toplevel
        PLACE_NAMES_CACHE,
        attach_export,
        clean_dir_for_jsonl,
        earlier_scrapes,
        resolve_scrape_out,
    )
    from .pipeline import scrape as run_scrape  # pylint: disable=import-outside-toplevel
    from .stats import load_dataframe, render, summarize  # pylint: disable=import-outside-toplevel

    today = date.today()
    n_days, plan = _plan_walk(export, days, since, until, today)
    driver = make_driver(serial=serial, prefer=prefer)  # before creating a run that stays empty

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
    result = run_scrape(
        driver,
        today=today,
        n_days=n_days,
        out_dir=raw_dir,
        on_error=on_error,
        only_days=plan.days if plan is not None else None,
    )
    typer.echo(
        f"Scraped {result.days_scraped} days"
        + (f" (walked {result.days_walked})" if plan is not None else "")
        + f" -> {result.output_path}"
        + (f" | failed: {result.days_failed}" if result.days_failed else "")
    )
    _continue_hint(result, plan)

    if clean_out is None and run_dir is None:
        normalize_out = clean_dir_for_jsonl(result.output_path)

    geocoder = _make_geocoder(geocode, nominatim_email)

    export_path = attach_export(export, result.output_path.parent) if export is not None else None
    typer.echo("\n[2/3] Normalizing dataset...")
    csv_path = build_dataset(
        result.output_path,
        export_path,
        normalize_out,
        geocoder=geocoder,
        names_cache=PLACE_NAMES_CACHE,
        earlier=earlier_scrapes(result.output_path),
    )

    typer.echo("\n[3/3] Summary:")
    stats_source = csv_path.with_suffix(".parquet")
    if not stats_source.exists():
        stats_source = csv_path
    df = load_dataframe(stats_source)
    typer.echo(render(summarize(df, top=top)))


@app.command("import")
def import_export(
    path: Annotated[
        Path,
        typer.Argument(
            help="Official Timeline export (Timeline.json) saved from the phone.",
            exists=True,
            dir_okay=False,
        ),
    ],
    run_dir: Annotated[
        Path | None,
        typer.Option(
            "--run",
            help=(
                "Existing run folder to attach the export to (e.g. one with a scrape, "
                "to merge both). Defaults to a new run under data/runs/."
            ),
            exists=True,
            file_okay=False,
        ),
    ] = None,
):
    """Import the official Timeline export into a run and build the clean dataset."""
    from .merge import build_dataset  # pylint: disable=import-outside-toplevel
    from .official import load_official_export  # pylint: disable=import-outside-toplevel
    from .paths import (  # pylint: disable=import-outside-toplevel
        PLACE_NAMES_CACHE,
        RAW_JSONL,
        attach_export,
        create_run_dir,
        earlier_scrapes,
        write_latest_marker,
    )

    try:
        load_official_export(path)  # validate before creating or touching any run
    except ValueError as exc:
        _exit_with_message(exc)

    if run_dir is None:
        run_dir = create_run_dir()
    else:
        write_latest_marker(run_dir)
    typer.echo(f"Export run: {run_dir}")

    export_path = attach_export(path, run_dir / "raw")
    jsonl = run_dir / "raw" / RAW_JSONL
    build_dataset(
        jsonl if jsonl.is_file() else None,
        export_path,
        run_dir / "clean",
        names_cache=PLACE_NAMES_CACHE,
        earlier=earlier_scrapes(jsonl),
    )


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
