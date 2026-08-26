"""
Investment One-Pager — a single-page PDF summary of a deal's full financial
underwriting: acquisition cost breakdown, exit price, net profit/ROI and
rental yield across every renovation tier, plus the Deal Score and a photo.

Built with reportlab (Platypus), reusing the photo-loading helpers from
app.spec_sheet rather than duplicating them.
"""
import datetime
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import models
from app.spec_sheet import _build_photo_section, _format_rooms


def _fmt_huf(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} HUF".replace(",", " ")


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _tier_rows(tiers: List[dict]) -> list:
    header = ["Tier", "Reno cost", "Safety buffer", "Total investment", "Net profit", "ROI", "Net yield"]
    rows = [header]
    for t in tiers:
        rows.append(
            [
                t["tier"].capitalize(),
                _fmt_huf(t["renovation_cost_huf"]),
                _fmt_huf(t["safety_buffer_huf"]),
                _fmt_huf(t["total_investment_huf"]),
                _fmt_huf(t["net_profit_huf"]),
                _fmt_pct(t["roi_percent"]),
                _fmt_pct(t["net_yield_percent"]),
            ]
        )
    return rows


def generate_investment_memo_pdf(
    prop: models.Property,
    benchmark: Optional[models.DistrictBenchmark],
    analysis,  # app.analyzer.PropertyAnalysis, loosely typed to avoid a hard import cycle
    deal_score: Optional[int] = None,
) -> bytes:
    """Returns the finished one-page PDF as bytes."""
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title=f"Investment Memo — {prop.title}",
    )
    styles = getSampleStyleSheet()
    story: list = []

    story.append(Paragraph("Investment One-Pager", styles["Title"]))
    meta_line = f"Generated {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    if deal_score is not None:
        meta_line += f"   |   Deal Score: {deal_score}/100"
    story.append(
        Paragraph(meta_line, ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.grey, fontSize=8))
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph(prop.title, styles["Heading1"]))
    if prop.address:
        story.append(Paragraph(prop.address, styles["Normal"]))
    story.append(Spacer(1, 6))

    summary_rows = [
        ["District", prop.district or "—"],
        ["Portal", prop.portal or "—"],
        ["Interior size", f"{prop.size_sqm:.1f} sqm" if prop.size_sqm else "—"],
        ["Balcony (weighted 50%)", f"{prop.balcony_sqm:.1f} sqm" if prop.balcony_sqm else "—"],
        ["Room count", _format_rooms(prop.rooms)],
        ["Condition", prop.condition or "—"],
        ["Asking price", _fmt_huf(prop.price_huf)],
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
    story.append(Spacer(1, 10))

    if analysis is not None:
        story.append(Paragraph("Acquisition & Exit", styles["Heading2"]))
        d = analysis.to_dict()
        acquisition_rows = [
            ["Purchase price", _fmt_huf(prop.price_huf)],
            ["Property transfer tax (illeték, 4%)", _fmt_huf(d["property_transfer_tax_huf"])],
            ["Legal / notary fee (1%)", _fmt_huf(d["legal_notary_fee_huf"])],
            ["Usable area (interior + 50% balcony)", f"{d['usable_area_sqm']:.1f} sqm"],
            ["Projected exit price", _fmt_huf(d["exit_price_huf"])],
        ]
        if benchmark is not None and benchmark.avg_price_sqm_renovated:
            acquisition_rows.append(
                ["District benchmark (renovated)", f"{benchmark.avg_price_sqm_renovated:,.0f} HUF/sqm".replace(",", " ")]
            )
        acquisition_table = Table(acquisition_rows, colWidths=[7 * cm, 10 * cm])
        acquisition_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(acquisition_table)
        story.append(Spacer(1, 10))

        story.append(Paragraph("Renovation Tiers — Cost, Profit & Yield", styles["Heading2"]))
        tier_table = Table(_tier_rows(d["tiers"]), colWidths=[2.2 * cm, 2.6 * cm, 2.6 * cm, 2.9 * cm, 2.6 * cm, 1.8 * cm, 2.0 * cm])
        tier_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(tier_table)
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                "Net yield assumes 20% of gross rent goes to management/maintenance/vacancy. "
                "Rental figures omitted where no district rent benchmark is on file.",
                ParagraphStyle("Note", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
            )
        )
        story.append(Spacer(1, 10))
    else:
        story.append(
            Paragraph(
                "No district benchmark available yet — full underwriting numbers can't be computed for this property.",
                styles["Italic"],
            )
        )
        story.append(Spacer(1, 10))

    story.append(Paragraph("Photo", styles["Heading2"]))
    story.extend(_build_photo_section((prop.images or [])[:1], max_images=1))

    doc.build(story)
    return buffer.getvalue()
