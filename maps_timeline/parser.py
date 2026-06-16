"""Parse the uiautomator XML dump of the Google Maps Routes screen.

Findings about the real UI (see the sample dumps):
- The Timeline is rendered in a WebView: each segment is an `android.widget.Button`
  whose text lives in the ``content-desc`` attribute (not in ``text``).
- Most of the day is present without scrolling, but the **last segment** (often the
  return visit with ``Hora de llegada``) is lazy-loaded: it only appears in the
  accessibility tree after scrolling the list down once. The scraper handles this
  in ``waits.dump_full_timeline``.
- Off-screen segments above the fold may appear with bounds ``[0,0][0,0]`` but
  their content-desc is populated anyway.
- Document order (the order nodes appear in) is chronological.
- Fields inside the content-desc are separated by ", " (comma + space), while
  decimals use a comma with no space ("2,4 km") => splitting on ", " is safe.

Note: the Spanish string literals and regexes below match the actual app UI
(which renders in Spanish), so they must not be translated.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # nosec B405 — trusted local adb / saved dumps only

from .models import DaySummary, DayTimeline, Segment, SegmentType, TimeAnchor

# Known transport modes that head an activity segment (Spanish UI strings).
_TRANSPORT_MODES = (
    "En automóvil",
    "A pie",
    "Caminando",
    "En bicicleta",
    "En motocicleta",
    "En transporte público",
    "En tren",
    "En autobús",
    "En subte",
    "En avión",
    "En barco",
    "Volando",
)

# content-desc of action / chrome buttons that are NOT segments (Spanish UI strings).
_ACTION_PREFIXES = (
    "Más opciones",
    "Editar",
    "Sí,",
    "Sí ",
    "No,",
    "Agregar",
    "Día anterior",
    "Día siguiente",
    "Cerrar",
    "Seleccionar el año",
    "mes anterior",
    "mes siguiente",
    "Se habilitó",
    "La función Rutas",
    "La capa de",
)

_TIME = r"\d{1,2}:\d{2}\s*[AP]M"
_RANGE_RE = re.compile(rf"De\s+({_TIME})\s+a\s+({_TIME})")
_DEPARTURE_RE = re.compile(rf"Hora de salida:\s*({_TIME})")
_ARRIVAL_RE = re.compile(rf"Hora de llegada:\s*({_TIME})")
_ALL_DAY_RE = re.compile(r"Todo el día")
_DISTANCE_RE = re.compile(r"\b(\d+(?:,\d+)?\s*(?:km|m))\b")
_DURATION_RE = re.compile(r"\b((?:\d+\s*h\s*)?\d+\s*min|\d+\s*h)\b")
_DATE_HEADER_RE = re.compile(r"^(Today|Yesterday|[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}, \d{4})$")
_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)]\[(\d+),(\d+)]")
# When the date header sits below this fraction of the screen, the sheet is not fully expanded.
_PANEL_EXPAND_HEADER_FRACTION = 0.40
# Fallback when a dump has no full-screen bounds (calibrated from the primary dev device).
DEFAULT_SCREEN_WIDTH = 1440
DEFAULT_SCREEN_HEIGHT = 3120
_MIN_INFERRED_SCREEN_WIDTH = 320
_MIN_INFERRED_SCREEN_HEIGHT = 480


def _is_action(desc: str) -> bool:
    """Return True when `desc` is a chrome/action button, not a Timeline segment."""
    return any(desc.startswith(p) for p in _ACTION_PREFIXES)


def _classify(desc: str) -> SegmentType:
    """Map a content-desc prefix to a SegmentType."""
    if desc.startswith("¿Visitaste"):
        return SegmentType.UNCONFIRMED_VISIT
    if desc.startswith("Visita desconocida"):
        return SegmentType.UNKNOWN_VISIT
    if desc.startswith("Modo de viaje faltante"):
        return SegmentType.MISSING_TRANSIT
    if any(desc.startswith(mode) for mode in _TRANSPORT_MODES):
        return SegmentType.ACTIVITY
    return SegmentType.PLACE_VISIT


def _parse_time(desc: str) -> tuple[TimeAnchor | None, str | None, str | None]:
    """Extract the time anchor and start/end times from a content-desc."""
    if m := _RANGE_RE.search(desc):
        return TimeAnchor.RANGE, m.group(1), m.group(2)
    if m := _DEPARTURE_RE.search(desc):
        return TimeAnchor.DEPARTURE, m.group(1), None
    if m := _ARRIVAL_RE.search(desc):
        return TimeAnchor.ARRIVAL, None, m.group(1)
    if _ALL_DAY_RE.search(desc):
        return TimeAnchor.ALL_DAY, None, None
    return None, None, None


def _strip_time_fields(desc: str) -> str:
    """Remove the time fragments to isolate name + address."""
    out = _RANGE_RE.sub("", desc)
    out = _DEPARTURE_RE.sub("", out)
    out = _ARRIVAL_RE.sub("", out)
    out = _ALL_DAY_RE.sub("", out)
    return out


def parse_segment(desc: str) -> Segment | None:
    """Turn a content-desc into a Segment, or None if it is an action button."""
    desc = desc.strip()
    if not desc or _is_action(desc):
        return None

    seg_type = _classify(desc)
    anchor, start, end = _parse_time(desc)

    # A real place/visit always carries a time anchor. If it has none and it is
    # not an activity, it is chrome/action that slipped through: discard it.
    is_activity = seg_type in (SegmentType.ACTIVITY, SegmentType.MISSING_TRANSIT)
    if anchor is None and not is_activity:
        return None

    seg = Segment(type=seg_type, time_anchor=anchor, start_time=start, end_time=end, raw_desc=desc)

    if is_activity:
        if m := _DURATION_RE.search(desc):
            seg.duration_text = m.group(1).strip()
        if m := _DISTANCE_RE.search(desc):
            seg.distance_text = m.group(1).strip()
        # The title is the first comma-separated field (transport mode or missing transit).
        seg.title = desc.split(",", 1)[0].strip()
        seg.needs_user_action = seg_type is SegmentType.MISSING_TRANSIT
        return seg

    # Places / visits: name before the time, address after it.
    rest = _strip_time_fields(desc)
    parts = [p.strip() for p in rest.split(",") if p.strip()]
    if parts:
        seg.title = parts[0]
        if len(parts) > 1:
            seg.address = ", ".join(parts[1:])

    if seg_type is SegmentType.UNCONFIRMED_VISIT:
        seg.title = re.sub(r"^¿Visitaste\s+", "", seg.title or "").rstrip("?")
        seg.confirmed = False
        seg.needs_user_action = True
    elif seg_type is SegmentType.UNKNOWN_VISIT:
        seg.needs_user_action = True
    else:
        seg.confirmed = True

    return seg


def _iter_button_descs(root: ET.Element):
    """Yield the content-desc of every Button in document order (chronological)."""
    for node in root.iter("node"):
        if node.get("class") == "android.widget.Button":
            desc = node.get("content-desc", "")
            if desc:
                yield desc


def parse_summary(root: ET.Element) -> DaySummary:
    """Read the summary bar (distance, duration, and visit count TextViews)."""
    summary = DaySummary()
    for node in root.iter("node"):
        if node.get("class") != "android.widget.TextView":
            continue
        text = (node.get("text") or "").strip()
        if not text:
            continue
        if m := re.fullmatch(r"(\d+)\s+visitas?", text):
            summary.visit_count = int(m.group(1))
        elif _DISTANCE_RE.fullmatch(text):
            summary.total_distance_text = text
        elif _DURATION_RE.fullmatch(text):
            summary.total_duration_text = text
    return summary


def read_header_text(root: ET.Element) -> str | None:
    """Return the date header text (e.g. "Sat Jun 6, 2026" / "Today")."""
    for node in root.iter("node"):
        text = (node.get("text") or "").strip()
        if text and _DATE_HEADER_RE.match(text):
            return text
    return None


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    """Parse ``[x1,y1][x2,y2]`` bounds into integer coordinates."""
    match = _BOUNDS_RE.match(bounds)
    if match is None:
        return None
    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def screen_size_from_dump(dump_xml: str) -> tuple[int, int]:
    """Infer the device screen size from full-screen bounds, with a calibrated fallback."""
    root = ET.fromstring(dump_xml)  # nosec B314
    origin_w = 0
    origin_h = 0
    max_x = 0
    max_y = 0
    for node in root.iter("node"):
        bounds = node.get("bounds")
        if bounds is None:
            continue
        box = _parse_bounds(bounds)
        if box is None:
            continue
        x1, y1, x2, y2 = box
        max_x = max(max_x, x2)
        max_y = max(max_y, y2)
        if x1 == 0 and y1 == 0:
            origin_w = max(origin_w, x2)
            origin_h = max(origin_h, y2)
    for width, height in ((origin_w, origin_h), (max_x, max_y)):
        if width >= _MIN_INFERRED_SCREEN_WIDTH and height >= _MIN_INFERRED_SCREEN_HEIGHT:
            return width, height
    return DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT


def date_header_top_y(dump_xml: str) -> int | None:
    """Return the top Y coordinate of the Timeline date header, if visible."""
    root = ET.fromstring(dump_xml)  # nosec B314
    for node in root.iter("node"):
        if node.get("class") != "android.widget.TextView":
            continue
        text = (node.get("text") or "").strip()
        if not text or not _DATE_HEADER_RE.match(text):
            continue
        bounds = node.get("bounds")
        if bounds is None:
            continue
        box = _parse_bounds(bounds)
        if box is not None:
            return box[1]
    return None


def timeline_list_present(dump_xml: str) -> bool:
    """Return True when the dump looks like the Timeline day view (not map/tabs only)."""
    root = ET.fromstring(dump_xml)  # nosec B314
    if read_header_text(root) is not None:
        return True
    if parse_summary(root).visit_count is not None:
        return True
    for node in root.iter("node"):
        if node.get("content-desc") == "Día anterior":
            return True
    return count_timeline_segments(dump_xml) > 0


def timeline_panel_collapsed(dump_xml: str) -> bool:
    """Return True when Timeline chrome is visible but the activity list is not expanded."""
    if not timeline_list_present(dump_xml):
        return False
    root = ET.fromstring(dump_xml)  # nosec B314
    summary = parse_summary(root)
    has_summary = (
        summary.visit_count is not None
        or summary.total_distance_text is not None
        or summary.total_duration_text is not None
    )
    if has_summary or count_timeline_segments(dump_xml) > 0:
        return False
    return True


def timeline_panel_needs_expand(dump_xml: str) -> bool:
    """Return True when the bottom sheet should be swiped up before scraping."""
    if not timeline_list_present(dump_xml):
        return False
    if timeline_panel_collapsed(dump_xml):
        return True
    root = ET.fromstring(dump_xml)  # nosec B314
    if count_timeline_segments(dump_xml) == 0 and (parse_summary(root).visit_count or 0) > 0:
        return True
    header_y = date_header_top_y(dump_xml)
    if header_y is None:
        return False
    _, screen_h = screen_size_from_dump(dump_xml)
    return header_y > int(screen_h * _PANEL_EXPAND_HEADER_FRACTION)


def parse_day(dump_xml: str, day) -> DayTimeline:
    """Parse a full day dump into a DayTimeline."""
    root = ET.fromstring(dump_xml)  # nosec B314
    segments = []
    for desc in _iter_button_descs(root):
        if seg := parse_segment(desc):
            segments.append(seg)
    return DayTimeline(
        day=day,
        header_text=read_header_text(root),
        summary=parse_summary(root),
        segments=segments,
    )


def count_timeline_segments(dump_xml: str) -> int:
    """Count parseable Timeline segments in a dump (used before/after scroll)."""
    root = ET.fromstring(dump_xml)  # nosec B314
    return sum(1 for desc in _iter_button_descs(root) if parse_segment(desc))


def timeline_anchor_flags(dump_xml: str) -> tuple[bool, bool]:
    """Return whether the dump includes departure and/or arrival time anchors."""
    has_departure = False
    has_arrival = False
    root = ET.fromstring(dump_xml)  # nosec B314
    for desc in _iter_button_descs(root):
        if seg := parse_segment(desc):
            if seg.time_anchor is TimeAnchor.DEPARTURE:
                has_departure = True
            elif seg.time_anchor is TimeAnchor.ARRIVAL:
                has_arrival = True
    return has_departure, has_arrival


def is_richer_timeline_dump(candidate: str, current: str) -> bool:
    """Return True when `candidate` is a strictly better scroll snapshot than `current`."""
    cand_count = count_timeline_segments(candidate)
    cur_count = count_timeline_segments(current)
    if cand_count > cur_count:
        return True
    if cand_count < cur_count:
        return False
    _, cand_arr = timeline_anchor_flags(candidate)
    cur_dep, cur_arr = timeline_anchor_flags(current)
    if cur_dep and cand_arr and not cur_arr:
        return True
    return False
