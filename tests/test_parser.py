"""Offline tests for the XML parser, using synthetic content-desc strings.

These do not need a device or a real dump: they exercise the pure parsing logic
against the Spanish UI strings the Google Maps app produces.
"""

from __future__ import annotations

from datetime import date

from maps_timeline.models import SegmentType, TimeAnchor
from maps_timeline.parser import (
    DEFAULT_SCREEN_HEIGHT,
    DEFAULT_SCREEN_WIDTH,
    count_timeline_segments,
    date_header_top_y,
    is_richer_timeline_dump,
    parse_day,
    parse_segment,
    screen_size_from_dump,
    timeline_anchor_flags,
    timeline_list_present,
    timeline_panel_collapsed,
    timeline_panel_needs_expand,
)
from tests.conftest import button_xml, day_dump_xml, text_xml


def test_parse_activity():
    """Parse a transport activity with distance, duration, and time range."""
    seg = parse_segment("En automóvil, 10 min, 2,4 km, De 4:49 PM a 4:59 PM")
    assert seg is not None
    assert seg.type is SegmentType.ACTIVITY
    assert seg.title == "En automóvil"
    assert seg.distance_text == "2,4 km"
    assert seg.duration_text == "10 min"
    assert (seg.start_time, seg.end_time) == ("4:49 PM", "4:59 PM")
    assert seg.time_anchor is TimeAnchor.RANGE


def test_parse_place_visit_with_range():
    """Parse a confirmed place visit with title, address, and time range."""
    seg = parse_segment("R&b cafe, De 4:59 PM a 6:36 PM, CJP, C. 4 366, B1902 La Plata")
    assert seg is not None
    assert seg.type is SegmentType.PLACE_VISIT
    assert seg.title == "R&b cafe"
    assert seg.address == "CJP, C. 4 366, B1902 La Plata"
    assert seg.confirmed is True


def test_parse_departure_and_arrival():
    """Parse first/last point anchors for departure and arrival times."""
    dep = parse_segment("C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell")
    arr = parse_segment("C. 29 5450, Hora de llegada: 9:38 PM, C. 29 5450, B1902 City Bell")
    assert dep is not None and dep.time_anchor is TimeAnchor.DEPARTURE
    assert dep.start_time == "4:08 PM" and dep.end_time is None
    assert arr is not None and arr.time_anchor is TimeAnchor.ARRIVAL
    assert arr.end_time == "9:38 PM" and arr.start_time is None


def test_parse_unconfirmed_visit():
    """Parse an unconfirmed visit prompt and mark it as needing user action."""
    seg = parse_segment(
        "¿Visitaste Facultad de Informática - UNLP?, De 4:39 PM a 4:49 PM, Calle 50"
    )
    assert seg is not None
    assert seg.type is SegmentType.UNCONFIRMED_VISIT
    assert seg.title == "Facultad de Informática - UNLP"
    assert seg.confirmed is False
    assert seg.needs_user_action is True


def test_parse_all_day_home_visit():
    """Parse a whole-day stay when Google shows 'Todo el día' instead of clock times."""
    seg = parse_segment(
        "¿Visitaste C. 29 5450?, Todo el día, C. 29 5450, B1902 City Bell, "
        "Provincia de Buenos Aires"
    )
    assert seg is not None
    assert seg.type is SegmentType.UNCONFIRMED_VISIT
    assert seg.time_anchor is TimeAnchor.ALL_DAY
    assert seg.title == "C. 29 5450"
    assert seg.address == "C. 29 5450, B1902 City Bell, Provincia de Buenos Aires"
    assert seg.start_time is None and seg.end_time is None
    assert seg.confirmed is False
    assert seg.needs_user_action is True


def test_parse_jun3_debug_dump():
    """Parse a day dump with a whole-day home visit and matching summary."""
    dump = day_dump_xml(
        text_xml("Wed Jun 3, 2026"),
        text_xml("1 visitas"),
        button_xml("C. 29 5450, Todo el día, C. 29 5450, B1902 City Bell"),
        button_xml("Día anterior", clickable=True),
    )
    day = parse_day(dump, date(2026, 6, 3))
    assert day.summary.visit_count == 1
    assert len(day.segments) == 1
    assert day.segments[0].title == "C. 29 5450"
    assert day.segments[0].time_anchor is TimeAnchor.ALL_DAY
    assert day.summary_matches() is True


def test_parse_missing_transit():
    """Parse a missing transit segment and flag it for user action."""
    seg = parse_segment("Modo de viaje faltante, 31 min, 14 km, De 4:08 PM a 4:39 PM")
    assert seg is not None
    assert seg.type is SegmentType.MISSING_TRANSIT
    assert seg.needs_user_action is True


def test_action_buttons_are_ignored():
    """Ignore navigation and confirmation buttons that are not Timeline data."""
    assert parse_segment("Más opciones") is None
    assert parse_segment("Día anterior") is None
    assert parse_segment("Sí, Facultad de Informática - UNLP, De 4:39 PM a 4:49 PM") is None


def _button(desc: str) -> str:
    """Build a synthetic Button node XML fragment for parser tests."""
    return f'<node class="android.widget.Button" content-desc="{desc}" bounds="[0,0][1,1]"/>'


def _text(value: str) -> str:
    """Build a synthetic TextView node XML fragment for parser tests."""
    return f'<node class="android.widget.TextView" text="{value}" bounds="[0,0][1,1]"/>'


def test_parse_day_orders_and_summarizes():
    """Parse a synthetic day dump in chronological order and read the summary."""
    xml = (
        "<hierarchy>"
        + _text("Sat Jun 6, 2026")
        + _text("18 km")
        + _text("5 visitas")
        + _button("C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell")
        + _button("En automóvil, 10 min, 2,4 km, De 4:49 PM a 4:59 PM")
        + _button("R&amp;b cafe, De 4:59 PM a 6:36 PM, CJP, C. 4 366")
        + _button("Más opciones")
        + "</hierarchy>"
    )
    day = parse_day(xml, date(2026, 6, 6))
    assert day.header_text == "Sat Jun 6, 2026"
    assert day.summary.visit_count == 5
    assert [s.type for s in day.segments] == [
        SegmentType.PLACE_VISIT,
        SegmentType.ACTIVITY,
        SegmentType.PLACE_VISIT,
    ]


def test_timeline_list_present_detects_day_view():
    """Detect the Timeline day view from the header, summary, or nav chrome."""
    day_view = (
        "<hierarchy>"
        + _text("Today")
        + _text("1 visitas")
        + _button("Día anterior")
        + "</hierarchy>"
    )
    assert timeline_list_present(day_view) is True
    assert timeline_list_present("<hierarchy>" + _text("2 visitas") + "</hierarchy>") is True
    assert timeline_list_present("<hierarchy>" + _button("Día anterior") + "</hierarchy>") is True
    assert timeline_list_present("<hierarchy/>") is False


def test_timeline_panel_collapsed_detects_map_only_sheet():
    """Detect when Timeline chrome is visible but the activity list is not expanded."""
    collapsed = "<hierarchy>" + _text("Today") + _button("Día anterior") + "</hierarchy>"
    expanded = (
        "<hierarchy>"
        + _text("Today")
        + _text("1 visitas")
        + _button("Día anterior")
        + "</hierarchy>"
    )
    assert timeline_panel_collapsed(collapsed) is True
    assert timeline_panel_collapsed(expanded) is False
    assert timeline_panel_collapsed("<hierarchy/>") is False


def test_timeline_panel_needs_expand_detects_half_open_sheet():
    """Request expansion when the date header sits too low on the screen."""
    half_open = (
        "<hierarchy>"
        + text_xml("Today", bounds="[0,1500][1440,1600]")
        + text_xml("1 visitas", bounds="[0,1600][1440,1700]")
        + button_xml("C. 1, Hora de salida: 4:08 PM, C. 1, City", bounds="[0,1800][1440,2000]")
        + "</hierarchy>"
    )
    fully_open = (
        "<hierarchy>"
        + text_xml("Today", bounds="[0,200][1440,300]")
        + text_xml("1 visitas", bounds="[0,300][1440,400]")
        + button_xml("C. 1, Hora de salida: 4:08 PM, C. 1, City", bounds="[0,500][1440,700]")
        + "</hierarchy>"
    )
    assert timeline_panel_needs_expand(half_open) is True
    assert timeline_panel_needs_expand(fully_open) is False


def test_screen_size_from_dump_defaults_without_bounds():
    """Fall back to a calibrated resolution when the dump has no full-screen bounds."""
    assert screen_size_from_dump("<hierarchy/>") == (DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT)


def test_screen_size_from_dump_ignores_placeholder_bounds():
    """Ignore tiny placeholder bounds and use the calibrated fallback instead."""
    xml = (
        "<hierarchy>"
        '<node class="android.widget.TextView" text="Today" bounds="[0,0][1,1]"/>'
        '<node class="android.widget.TextView" text="1 visitas" bounds="[0,0][1,1]"/>'
        "</hierarchy>"
    )
    assert screen_size_from_dump(xml) == (DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT)


def test_screen_size_from_dump_skips_invalid_nodes():
    """Ignore nodes with missing or invalid bounds while scanning the screen size."""
    xml = (
        "<hierarchy>"
        '<node class="android.widget.FrameLayout"/>'
        '<node bounds="bad"/>'
        '<node bounds="[0,0][1080,2400]"/>'
        "</hierarchy>"
    )
    assert screen_size_from_dump(xml) == (1080, 2400)


def test_date_header_top_y_ignores_invalid_bounds():
    """Skip date headers whose bounds cannot be parsed."""
    xml = (
        "<hierarchy>"
        + _text("Today").replace('bounds="[0,0][1,1]"', 'bounds="bad"')
        + "</hierarchy>"
    )
    assert date_header_top_y(xml) is None


def test_date_header_top_y_requires_bounds():
    """Return None when the date header has no bounds attribute."""
    xml = '<hierarchy><node class="android.widget.TextView" text="Today"/></hierarchy>'
    assert date_header_top_y(xml) is None


def test_date_header_top_y_ignores_non_header_text():
    """Ignore TextViews that are not Timeline date headers."""
    xml = (
        "<hierarchy>"
        '<node class="android.widget.TextView" text="1 visitas" bounds="[0,0][1,1]"/>'
        "</hierarchy>"
    )
    assert date_header_top_y(xml) is None


def test_timeline_panel_needs_expand_false_without_timeline():
    """Do not swipe when the dump is not the Timeline day view."""
    assert timeline_panel_needs_expand("<hierarchy/>") is False


def test_count_timeline_segments():
    """Count only parseable Timeline buttons, ignoring chrome actions."""
    xml = (
        "<hierarchy>"
        + _button("C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell")
        + _button("En automóvil, 10 min, 2,4 km, De 4:49 PM a 4:59 PM")
        + _button("Más opciones")
        + "</hierarchy>"
    )
    assert count_timeline_segments(xml) == 2


def test_timeline_anchor_flags_detects_home_endpoints():
    """Detect departure and arrival anchors for a round-trip day."""
    with_both = (
        "<hierarchy>"
        + _button("C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell")
        + _button("C. 29 5450, Hora de llegada: 9:38 PM, C. 29 5450, B1902 City Bell")
        + "</hierarchy>"
    )
    without_arrival = (
        "<hierarchy>"
        + _button("C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell")
        + _button("En automóvil, 42 min, 13 km, De 8:55 PM a 9:38 PM")
        + "</hierarchy>"
    )
    assert timeline_anchor_flags(with_both) == (True, True)
    assert timeline_anchor_flags(without_arrival) == (True, False)


def test_is_richer_timeline_dump_prefers_arrival_at_equal_count():
    """Prefer a snapshot that includes the return-home arrival when counts match."""
    without_arrival = (
        "<hierarchy>"
        + _button("C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell")
        + _button("En automóvil, 42 min, 13 km, De 8:55 PM a 9:38 PM")
        + _button("R&amp;b cafe, De 4:59 PM a 6:36 PM, CJP, C. 4 366, B1902 La Plata")
        + "</hierarchy>"
    )
    with_arrival = (
        "<hierarchy>"
        + _button("En automóvil, 42 min, 13 km, De 8:55 PM a 9:38 PM")
        + _button("R&amp;b cafe, De 4:59 PM a 6:36 PM, CJP, C. 4 366, B1902 La Plata")
        + _button("C. 29 5450, Hora de llegada: 9:38 PM, C. 29 5450, B1902 City Bell")
        + "</hierarchy>"
    )
    assert count_timeline_segments(without_arrival) == count_timeline_segments(with_arrival)
    assert is_richer_timeline_dump(with_arrival, without_arrival) is True
    assert is_richer_timeline_dump(without_arrival, with_arrival) is False
    assert is_richer_timeline_dump(without_arrival, without_arrival) is False


def test_is_richer_timeline_dump_prefers_more_segments():
    """Prefer a dump with strictly more parseable segments."""
    shorter = (
        "<hierarchy>"
        + _button("En automóvil, 10 min, 2,4 km, De 4:49 PM a 4:59 PM")
        + "</hierarchy>"
    )
    longer = (
        "<hierarchy>"
        + _button("En automóvil, 10 min, 2,4 km, De 4:49 PM a 4:59 PM")
        + _button("C. 29 5450, Hora de llegada: 9:38 PM, C. 29 5450, B1902 City Bell")
        + "</hierarchy>"
    )
    assert is_richer_timeline_dump(longer, shorter) is True
    assert is_richer_timeline_dump(shorter, longer) is False


def test_parse_round_trip_day_includes_arrival():
    """Parse a return visit anchored on Hora de llegada at the end of the day."""
    xml = (
        "<hierarchy>"
        + _text("Sun Jun 7, 2026")
        + _text("3 visitas")
        + _button("C. 29 5450, Hora de salida: 1:49 PM, C. 29 5450, B1902 City Bell")
        + _button("En automóvil, 26 min, 10 km, De 1:49 PM a 2:15 PM")
        + _button("¿Visitaste C. 12 630?, De 2:15 PM a 7:57 PM, C. 12 630, La Plata")
        + _button("En automóvil, 21 min, 9,8 km, De 7:57 PM a 8:18 PM")
        + _button("C. 29 5450, Hora de llegada: 8:18 PM, C. 29 5450, B1902 City Bell")
        + "</hierarchy>"
    )
    day = parse_day(xml, date(2026, 6, 7))
    assert day.summary.visit_count == 3
    assert day.place_visits == 3
    assert day.summary_matches() is True
    assert day.segments[-1].time_anchor is TimeAnchor.ARRIVAL
    assert day.segments[-1].end_time == "8:18 PM"


def test_parse_unknown_visit():
    """Parse an unknown visit and mark it for user action."""
    seg = parse_segment("Visita desconocida, De 1:00 PM a 2:00 PM, Somewhere")
    assert seg is not None
    assert seg.type is SegmentType.UNKNOWN_VISIT
    assert seg.needs_user_action is True
    assert seg.confirmed is None


def test_parse_walking_activity():
    """Classify walking activities using alternate transport prefixes."""
    seg = parse_segment("A pie, 5 min, 500 m, De 1:00 PM a 1:05 PM")
    assert seg is not None
    assert seg.type is SegmentType.ACTIVITY
    assert seg.title == "A pie"


def test_parse_place_without_time_is_discarded():
    """Discard place-like strings that lack a time anchor."""
    assert parse_segment("Only a title, no time here") is None


def test_parse_empty_desc_is_discarded():
    """Discard empty content-desc strings."""
    assert parse_segment("   ") is None


def test_parse_activity_without_optional_fields():
    """Parse activities even when duration or distance are missing."""
    seg = parse_segment("En automóvil, De 4:49 PM a 4:59 PM")
    assert seg is not None
    assert seg.duration_text is None
    assert seg.distance_text is None


def test_parse_place_with_title_only():
    """Parse a visit that has a title but no separate address field."""
    seg = parse_segment("Cafe, De 4:59 PM a 5:59 PM")
    assert seg is not None
    assert seg.title == "Cafe"
    assert seg.address is None


def test_parse_day_reads_relative_header_and_duration_summary():
    """Parse Today/Yesterday headers and duration summary TextViews."""
    xml = (
        "<hierarchy>"
        + _text("Yesterday")
        + _text("1 h 15 min")
        + _text("2 visitas")
        + _button("Cafe, De 4:59 PM a 5:59 PM, Main 1")
        + '<node class="android.widget.Button" bounds="[0,0][1,1]"/>'
        + "</hierarchy>"
    )
    day = parse_day(xml, date(2026, 6, 10))
    assert day.header_text == "Yesterday"
    assert day.summary.total_duration_text == "1 h 15 min"
    assert day.summary.visit_count == 2
    assert len(day.segments) == 1


def test_parse_place_with_empty_title_parts():
    """Keep the segment when the title cannot be split from the address."""
    seg = parse_segment("De 4:49 PM a 4:59 PM")
    assert seg is not None
    assert seg.title is None
    assert seg.address is None


def test_parse_day_skips_blank_text_nodes():
    """Ignore TextView nodes whose text attribute is empty."""
    xml = (
        "<hierarchy>"
        + _text("")
        + _text("Today")
        + _button("Cafe, De 4:59 PM a 5:59 PM, Main 1")
        + "</hierarchy>"
    )
    day = parse_day(xml, date(2026, 6, 10))
    assert day.header_text == "Today"
