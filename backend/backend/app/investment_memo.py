"""
Deal Memo — a single-page, executive-level PDF summary of one property's
automated underwriting verdict (app/services/valuation_agent.py): asking
price, district baseline, discount to market, renovation budget, all-in
investment, projected exit value, net flip profit/ROI, Deal Score, and an
auto-generated Investment Thesis paragraph.

This is distinct from app/spec_sheet.py's Contractor Spec Sheet (floor plan
+ photos + quoting checklist) and from the interactive Light/Medium/Full
renovation-tier tool in app/analyzer.py (still used live in the dashboard
UI) — this memo surfaces the underwriting *agent's* persisted numbers only,
"as of the last scan" (see underwriting_updated_at), for handing to a
partner/lender.

Built with reportlab (Platypus).
"""
import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import models


def _fmt_huf(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} HUF".replace(",", " ")


def _fmt_eur(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"€{value:,.0f}".replace(",", " ")


def _fmt_huf_sqm(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} HUF/sqm".replace(",", " ")


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _fmt_sqm(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.1f} sqm"


def _district_baseline_and_discount(
    prop: models.Property, benchmark: Optional[models.DistrictBenchmark]
):
    """
    District Baseline Median (HUF/sqm) and Discount to Market (%), computed
    against benchmark.avg_price_sqm_renovated — the exact same reference
    app/services/valuation_agent.py uses for its exit-price and discount
    math, so this figure always agrees with the persisted underwriting
    numbers below it.
    """
    if benchmark is None or benchmark.avg_price_sqm_renovated is None or not prop.price_per_sqm:
        return None, None
    median = benchmark.avg_price_sqm_renovated
    discount = (median - prop.price_per_sqm) / median * 100
    return median, round(discount, 2)


def _investment_thesis(
    prop: models.Property,
    district_baseline: Optional[float],
    discount_percent: Optional[float],
) -> str:
    if prop.underwriting_updated_at is None:
        return (
            "This listing has not yet been processed by the automated underwriting agent — figures above "
            "reflect asking-price and specs only. Run a market scan, or POST /properties/{}/underwrite, to "
            "generate a full underwriting verdict.".format(prop.id)
        )

    if prop.underwriting_status == "no_benchmark" or district_baseline is None:
        return (
            "No district benchmark is on file for this property yet, so a full underwriting verdict "
            "(exit value, profit, ROI) could not be computed. Asking price and renovation budget above are "
            "still based on the listing's own data."
        )

    district = prop.district or "this district"
    sqm = f"{prop.size_sqm:.0f} sqm" if prop.size_sqm else "unknown size"
    rooms = f"{prop.rooms:g}-room" if prop.rooms else ""
    direction = "below" if (discount_percent or 0) >= 0 else "above"

    sentence_1 = (
        f"This {rooms} {sqm} property in District {district} is priced {abs(discount_percent):.1f}% {direction} "
        f"the district's turnkey median of {_fmt_huf_sqm(district_baseline)}."
        if discount_percent is not None
        else f"This {rooms} {sqm} property is located in District {district}."
    )

    if prop.underwriting_total_investment_huf and prop.underwriting_market_value_huf:
        sentence_2 = (
            f" After an estimated {_fmt_huf(prop.underwriting_renovation_cost_huf)} renovation, acquisition tax "
            f"and closing costs, the all-in investment is {_fmt_huf(prop.underwriting_total_investment_huf)} "
            f"against a projected post-renovation exit value of {_fmt_huf(prop.underwriting_market_value_huf)}, "
            f"net of a 3% broker fee on sale."
        )
    else:
        sentence_2 = ""

    if prop.underwriting_net_profit_huf is not None and prop.underwriting_flip_roi_percent is not None:
        outcome = "a projected net profit of" if prop.underwriting_net_profit_huf >= 0 else "a projected net loss of"
        sentence_3 = (
            f" That implies {outcome} {_fmt_huf(prop.underwriting_net_profit_huf)} "
            f"({_fmt_pct(prop.underwriting_flip_roi_percent)} net ROI)."
        )
    else:
        sentence_3 = ""

    tag_sentences = {
        "High Potential Flip": " The agent flags this as a High Potential Flip candidate given its strong projected ROI.",
        "Buy & Hold Yield": " The agent flags this as a Buy & Hold Yield candidate given its rental income profile.",
    }
    sentence_4 = tag_sentences.get(prop.underwriting_confidence_tag or "", "")

    risk_sentences = {
        "overpriced": " Caution: asking price is above the district's turnkey median.",
        "below_hurdle_roi": " Caution: projected flip ROI falls below the fund's 12% minimum hurdle rate.",
    }
    sentence_5 = ""
    if prop.underwriting_status and prop.underwriting_status.startswith("risk:"):
        reasons = prop.underwriting_status.replace("risk:", "").split(",")
        sentence_5 = "".join(risk_sentences.get(r, "") for r in reasons)

    return (sentence_1 + sentence_2 + sentence_3 + sentence_4 + sentence_5).strip()


def generate_investment_memo_pdf(
    prop: models.Property,
    benchmark: Optional[models.DistrictBenchmark],
    eur_huf_rate: float,
) -> bytes:
    """Returns the finished one-page Deal Memo PDF as bytes."""
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title=f"Deal Memo — {prop.title}",
    )
    styles = getSampleStyleSheet()
    story: list = []

    # --- Header -------------------------------------------------------
    story.append(Paragraph("Deal Memo", styles["Title"]))
    story.append(Paragraph(prop.title or "Untitled listing", styles["Heading1"]))

    header_bits = [f"District {prop.district}" if prop.district else None]
    header_line = "  |  ".join(b for b in header_bits if b)
    if header_line:
        story.append(Paragraph(header_line, styles["Normal"]))
    if prop.url:
        story.append(
            Paragraph(
                f'<link href="{prop.url}">{prop.url}</link>',
                ParagraphStyle("Url", parent=styles["Normal"], textColor=colors.HexColor("#2563eb"), fontSize=8),
            )
        )
    story.append(
        Paragraph(
            f"Generated {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.grey, fontSize=8),
        )
    )
    story.append(Spacer(1, 12))

    # --- Core specs -----------------------------------------------------
    story.append(Paragraph("Core Specs", styles["Heading2"]))
    price_eur = prop.price_eur if prop.price_eur is not None else (
        prop.price_huf / eur_huf_rate if prop.price_huf else None
    )
    core_rows = [
        ["Asking price", f"{_fmt_huf(prop.price_huf)}   ({_fmt_eur(price_eur)})"],
        ["Total sqm", _fmt_sqm(prop.size_sqm)],
        ["Rooms", f"{prop.rooms:g}" if prop.rooms else "—"],
        ["Price / sqm", _fmt_huf_sqm(prop.price_per_sqm)],
    ]
    core_table = Table(core_rows, colWidths=[5 * cm, 12 * cm])
    core_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(core_table)
    story.append(Spacer(1, 12))

    # --- Underwriting breakdown -----------------------------------------
    story.append(Paragraph("Underwriting Breakdown", styles["Heading2"]))
    district_baseline, discount_percent = _district_baseline_and_discount(prop, benchmark)
    net_profit_eur = (
        prop.underwriting_net_profit_huf / eur_huf_rate if prop.underwriting_net_profit_huf is not None else None
    )

    underwriting_rows = [
        ["District baseline median", _fmt_huf_sqm(district_baseline)],
        ["Discount to market", _fmt_pct(discount_percent)],
        ["Estimated renovation budget", _fmt_huf(prop.underwriting_renovation_cost_huf)],
        ["All-in investment", _fmt_huf(prop.underwriting_total_investment_huf)],
        ["Projected post-renovation exit value", _fmt_huf(prop.underwriting_market_value_huf)],
        [
            "Projected net flip profit",
            f"{_fmt_huf(prop.underwriting_net_profit_huf)}   ({_fmt_eur(net_profit_eur)})",
        ],
        ["Projected net ROI", _fmt_pct(prop.underwriting_flip_roi_percent)],
        [
            "Deal Score",
            f"{prop.underwriting_deal_score}/100" if prop.underwriting_deal_score is not None else "—",
        ],
    ]
    underwriting_table = Table(underwriting_rows, colWidths=[7 * cm, 10 * cm])
    profit_row_index = 5
    score_row_index = 7
    table_style = [
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#eeeeee")),
        ("FONTNAME", (1, score_row_index), (1, score_row_index), "Helvetica-Bold"),
        ("FONTSIZE", (1, score_row_index), (1, score_row_index), 12),
    ]
    if prop.underwriting_net_profit_huf is not None:
        profit_color = colors.HexColor("#059669") if prop.underwriting_net_profit_huf >= 0 else colors.HexColor("#dc2626")
        table_style.append(("TEXTCOLOR", (1, profit_row_index), (1, profit_row_index), profit_color))
        table_style.append(("FONTNAME", (1, profit_row_index), (1, profit_row_index), "Helvetica-Bold"))
    underwriting_table.setStyle(TableStyle(table_style))
    story.append(underwriting_table)

    if prop.underwriting_status and prop.underwriting_status.startswith("risk:"):
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                "⚠ Risk flagged: " + prop.underwriting_status.replace("risk:", "").replace(",", ", "),
                ParagraphStyle("Risk", parent=styles["Normal"], textColor=colors.HexColor("#dc2626"), fontSize=8.5),
            )
        )
    if prop.underwriting_updated_at is not None:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"Underwriting as of last scan: {prop.underwriting_updated_at.strftime('%Y-%m-%d %H:%M UTC')}. "
                "Uses a condition-based renovation estimate, 4% acquisition tax + 1.5% legal/closing, and a 3% "
                "broker fee on exit.",
                ParagraphStyle("Note", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
            )
        )
    story.append(Spacer(1, 14))

    # --- Investment thesis ------------------------------------------------
    story.append(Paragraph("Investment Thesis", styles["Heading2"]))
    story.append(Paragraph(_investment_thesis(prop, district_baseline, discount_percent), styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
