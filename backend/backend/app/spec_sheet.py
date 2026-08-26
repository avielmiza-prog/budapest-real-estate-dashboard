"""
Contractor Spec Sheet — a printable PDF summary of one property for handing
to a contractor doing an on-site quote: floor space, room count, current
photos, and a category-by-category checklist with blank space for their
notes and cost estimates.

Built with reportlab (Platypus) — no external network access needed except
to fetch the property's own photos, which is done defensively (short
timeout, skips anything that fails rather than aborting the whole sheet).

NOTE on characters: per the pdf skill's guidance, this deliberately avoids
Unicode glyphs outside Helvetica's built-in Latin-1 range (box-drawing
checkboxes, etc.) — they render as solid black boxes / .notdef glyphs in
reportlab's base14 fonts. Checkboxes are drawn as plain ASCII "[ ]".
"""
import datetime
import io
import urllib.request
from typing import List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app import models

# ---------------------------------------------------------------------------
# The checklist itself — tune this as you learn what your contractors
# actually want to see. Organized the way a contractor would walk the unit.
# ---------------------------------------------------------------------------

CONTRACTOR_CHECKLIST: List[Tuple[str, List[str]]] = [
    (
        "Structural & General Condition",
        [
            "Identify load-bearing walls before quoting any wall removal (permit required in HU for structural changes)",
            "Check ceiling height and note any visible sagging, cracks, or water staining",
            "Inspect visible cracks in walls/facade — hairline vs. structural",
            "Note building age/era (relevant for asbestos-containing materials in pre-1990s Budapest buildings)",
            "Check floor levelness (self-leveling compound needed before new flooring?)",
        ],
    ),
    (
        "Electrical",
        [
            "Inspect fuse/breaker panel — age, capacity (amps), breaker vs. fuse type",
            "Check wiring type where visible (aluminum vs. copper) and overall condition",
            "Count existing outlets/switches per room; note any missing where needed",
            "Check for grounding (earthing) on outlets, especially kitchen/bathroom",
            "Note existing lighting fixtures to keep, replace, or add",
        ],
    ),
    (
        "Plumbing & Water",
        [
            "Identify pipe material (copper/PEX/old galvanized steel) and visible corrosion",
            "Test water pressure at kitchen and bathroom taps",
            "Check boiler/water heater age, type (gas combi vs. electric), and condition",
            "Inspect for visible leaks, water stains, or damp/mold near pipes",
            "Confirm shut-off valve locations and condition",
        ],
    ),
    (
        "Heating & Ventilation",
        [
            "Count and inspect radiators — condition, age, individual thermostatic valves",
            "Confirm heating type (district heating/gas/electric) and metering",
            "Check bathroom/kitchen ventilation (natural shaft vs. mechanical extractor)",
            "Note presence/condition of any air conditioning units",
        ],
    ),
    (
        "Windows & Doors",
        [
            "Check glazing type (single/double/triple) per window",
            "Test operation and seals on all windows and exterior doors",
            "Note frame material and condition (wood/PVC/aluminum)",
            "Inspect interior door condition and hardware",
        ],
    ),
    (
        "Flooring",
        [
            "Note existing flooring type per room (parquet/tile/laminate/carpet)",
            "Assess subfloor condition where flooring will be replaced",
            "Check for unevenness, squeaks, or damage requiring subfloor work",
        ],
    ),
    (
        "Kitchen",
        [
            "Assess existing cabinetry — keep, reface, or full replace",
            "Check gas/electric hookups and hood/extraction venting",
            "Inspect countertop and backsplash condition",
            "Confirm water supply and drain locations relative to planned layout",
        ],
    ),
    (
        "Bathroom(s)",
        [
            "Inspect waterproofing/tanking behind existing tile (if accessible)",
            "Check tile condition, grout, and any signs of moisture ingress",
            "Assess fixtures (toilet, sink, tub/shower) for reuse vs. replacement",
            "Confirm ventilation/extractor fan presence and function",
        ],
    ),
    (
        "Walls, Ceilings & Surfaces",
        [
            "Note paint/wallpaper condition and number of coats likely needed",
            "Check for damp patches, especially on exterior-facing and bathroom-adjacent walls",
            "Flag any surfaces needing plaster repair before painting",
        ],
    ),
    (
        "Building & Access (logistics for quoting)",
        [
            "Floor number and lift availability/size (affects material delivery cost)",
            "Staircase width if lift unavailable or too small for materials",
            "Courtyard/street access for waste removal and deliveries",
            "Building rules on working hours / noise (common in Budapest co-op buildings)",
        ],
    ),
    (
        "Utilities, Permits & Safety",
        [
            "Confirm individual vs. shared utility meters (gas/electric/water)",
            "Flag any work requiring a building permit (structural, gas line changes)",
            "Note any suspected asbestos-containing materials (do not disturb — test first)",
            "Check smoke detector / gas detector presence",
        ],
    ),
]


def _download_image_bytes(url: str, timeout: float = 6.0, max_bytes: int = 8_000_000) -> Optional[bytes]:
    """Best-effort fetch. Returns None on any failure — one bad photo URL shouldn't break the sheet."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (spec-sheet-generator)"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            return data
    except Exception:  # noqa: BLE001 - genuinely want to swallow any network/format error here
        return None


def _build_photo_section(image_urls: List[str], max_images: int = 6) -> list:
    """Returns Platypus flowables: a grid of photos, or a note if none could be loaded."""
    styles = getSampleStyleSheet()
    flowables: list = []

    if not image_urls:
        flowables.append(Paragraph("No photos on file for this listing.", styles["Italic"]))
        return flowables

    urls_to_try = image_urls[:max_images]
    cell_width = 5.5 * cm
    loaded_cells = []

    for url in urls_to_try:
        data = _download_image_bytes(url)
        if data is None:
            continue
        try:
            reader = ImageReader(io.BytesIO(data))
            iw, ih = reader.getSize()
            if iw <= 0 or ih <= 0:
                continue
            height = cell_width * ih / iw
            loaded_cells.append(Image(io.BytesIO(data), width=cell_width, height=height))
        except Exception:  # noqa: BLE001 - a corrupt/unsupported image shouldn't break the sheet
            continue

    if not loaded_cells:
        flowables.append(
            Paragraph(
                f"{len(urls_to_try)} photo URL(s) on file, but none could be downloaded when this sheet was generated.",
                styles["Italic"],
            )
        )
        return flowables

    rows = [loaded_cells[i : i + 3] for i in range(0, len(loaded_cells), 3)]
    # pad the last row so Table doesn't choke on ragged rows
    if rows and len(rows[-1]) < 3:
        rows[-1] = rows[-1] + [""] * (3 - len(rows[-1]))

    photo_table = Table(rows, colWidths=[cell_width + 0.3 * cm] * 3)
    photo_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    flowables.append(photo_table)

    skipped = len(urls_to_try) - len(loaded_cells)
    if skipped:
        flowables.append(Spacer(1, 4))
        flowables.append(Paragraph(f"({skipped} photo(s) could not be downloaded)", getSampleStyleSheet()["Italic"]))

    if len(image_urls) > max_images:
        flowables.append(Spacer(1, 4))
        flowables.append(
            Paragraph(f"+ {len(image_urls) - max_images} more photo(s) on the original listing.", getSampleStyleSheet()["Italic"])
        )

    return flowables


def _build_checklist_section(styles) -> list:
    flowables: list = []
    item_style = ParagraphStyle("ChecklistItem", parent=styles["Normal"], fontSize=9, leading=12)

    header_style = ParagraphStyle("ChecklistHeader", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    header_table = Table(
        [[Paragraph("Item", header_style), Paragraph("Contractor notes / cost estimate (HUF)", header_style)]],
        colWidths=[11.5 * cm, 5.5 * cm],
    )
    header_table.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    flowables.append(header_table)
    flowables.append(Spacer(1, 2))

    for category, items in CONTRACTOR_CHECKLIST:
        flowables.append(Paragraph(category, styles["Heading3"]))
        rows = [[Paragraph(f"[ ]  {item}", item_style), ""] for item in items]
        table = Table(rows, colWidths=[11.5 * cm, 5.5 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("LINEAFTER", (0, 0), (0, -1), 0.5, colors.HexColor("#dddddd")),
                ]
            )
        )
        flowables.append(table)
        flowables.append(Spacer(1, 6))

    return flowables


def generate_spec_sheet_pdf(
    prop: models.Property,
    benchmark: Optional[models.DistrictBenchmark] = None,
    analysis=None,  # app.analyzer.PropertyAnalysis, kept loosely typed to avoid a hard import cycle
) -> bytes:
    """Returns the finished PDF as bytes, ready to hand back as an HTTP response body."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title=f"Contractor Spec Sheet — {prop.title}",
    )
    styles = getSampleStyleSheet()
    story: list = []

    story.append(Paragraph("Contractor Spec Sheet", styles["Title"]))
    story.append(
        Paragraph(
            f"Generated {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.grey, fontSize=8),
        )
    )
    story.append(Spacer(1, 10))

    story.append(Paragraph(prop.title, styles["Heading1"]))
    if prop.address:
        story.append(Paragraph(prop.address, styles["Normal"]))
    story.append(Spacer(1, 8))

    summary_rows = [
        ["District", prop.district or "—"],
        ["Floor space", f"{prop.size_sqm:.1f} sqm" if prop.size_sqm else "—"],
        ["Room count", _format_rooms(prop.rooms)],
        ["Condition (as listed)", prop.condition or "—"],
        ["Asking price", f"{prop.price_huf:,.0f} HUF".replace(",", " ") if prop.price_huf else "—"],
        ["Price / sqm", f"{prop.price_per_sqm:,.0f} HUF/sqm".replace(",", " ") if prop.price_per_sqm else "—"],
    ]
    if prop.url:
        summary_rows.append(["Source listing", prop.url])

    summary_table = Table(summary_rows, colWidths=[4.5 * cm, 12.5 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 6))

    if benchmark is not None or analysis is not None:
        context_lines = []
        if benchmark is not None:
            if benchmark.avg_price_sqm_raw:
                context_lines.append(f"District avg. (unrenovated): {benchmark.avg_price_sqm_raw:,.0f} HUF/sqm".replace(",", " "))
            if benchmark.avg_price_sqm_renovated:
                context_lines.append(f"District avg. (renovated): {benchmark.avg_price_sqm_renovated:,.0f} HUF/sqm".replace(",", " "))
        if analysis is not None:
            best = analysis.best_tier()
            if best is not None and best.roi_percent is not None:
                context_lines.append(f"Best-case renovation ROI ({best.tier} tier): {best.roi_percent:.1f}%")
        if context_lines:
            story.append(Paragraph("Investment context: " + "  |  ".join(context_lines), ParagraphStyle(
                "Context", parent=styles["Normal"], fontSize=8, textColor=colors.grey
            )))
            story.append(Spacer(1, 10))

    story.append(Paragraph("Photos", styles["Heading2"]))
    story.extend(_build_photo_section(prop.images or []))
    story.append(Spacer(1, 12))

    story.append(Paragraph("On-Site Quoting Checklist", styles["Heading2"]))
    story.append(
        Paragraph(
            "For the contractor: check off each item during the walkthrough and note cost estimates in the right-hand column.",
            ParagraphStyle("Instructions", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
        )
    )
    story.append(Spacer(1, 6))
    story.extend(_build_checklist_section(styles))

    doc.build(story)
    return buffer.getvalue()


def _format_rooms(rooms: Optional[float]) -> str:
    if rooms is None:
        return "—"
    if float(rooms).is_integer():
        return str(int(rooms))
    whole = int(rooms)
    half = 1 if (rooms - whole) >= 0.5 else 0
    return f"{whole}+{half}" if half else str(rooms)
