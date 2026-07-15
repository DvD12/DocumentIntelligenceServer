"""Shared reportlab boilerplate for the Meridian corpus PDFs.

Every generated PDF gets realistic chaff — a repeated header line, a footer with
page numbers — plus font sizes tuned so the app's PDF heading heuristic
(size > 1.15x body median, < 80 chars, no trailing period) detects H1/H2:
body 10pt, H1 16pt, H2 13pt, header/footer 8pt, table cells 9pt.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

_BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=10, leading=15, spaceAfter=7)
_H1 = ParagraphStyle(
    "H1", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceBefore=14, spaceAfter=8
)
_H2 = ParagraphStyle(
    "H2", fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=10, spaceAfter=6
)
_CELL = ParagraphStyle("Cell", fontName="Helvetica", fontSize=9, leading=12)
_CELL_HDR = ParagraphStyle("CellHdr", fontName="Helvetica-Bold", fontSize=9, leading=12)


def h1(text: str) -> Paragraph:
    return Paragraph(text, _H1)


def h2(text: str) -> Paragraph:
    return Paragraph(text, _H2)


def p(text: str) -> Paragraph:
    return Paragraph(text, _BODY)


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(i, _BODY), leftIndent=12) for i in items],
        bulletType="bullet", start="-",
    )


def table(rows: list[list[str]], col_widths: list[float] | None = None) -> Table:
    """First row is the header row."""
    data = [[Paragraph(c, _CELL_HDR) for c in rows[0]]] + [
        [Paragraph(c, _CELL) for c in row] for row in rows[1:]
    ]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f6")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def spacer(height_cm: float = 0.3) -> Spacer:
    return Spacer(1, height_cm * cm)


def contents(section_titles: list[str]) -> list:
    """Cover-page table of contents, then a page break.

    TOC lines repeat heading text at body size — deliberate chaff: the heading
    heuristic must not misdetect them, and retrieval must prefer the real
    sections over the listing.
    """
    return [
        h1("Contents"),
        *[p(t) for t in section_titles],
        PageBreak(),
    ]


def revision_history(rows: list[list[str]]) -> list:
    """Standard closing section: [version, date, change] rows."""
    return [
        h1("Revision history"),
        table([["Version", "Date", "Change"], *rows]),
        spacer(),
    ]


def build_pdf(filename: str, doc_ref: str, elements: list) -> Path:
    """Render `elements` to docs/<filename> with header/footer chaff on every page."""
    out = DOCS_DIR / filename

    def decorate(canvas, _doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, A4[1] - 1.1 * cm, "Meridian Financial Group - Internal")
        canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.1 * cm, doc_ref)
        canvas.drawString(2 * cm, 1.1 * cm, "Classification: Internal - Restricted")
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=doc_ref,
    )
    doc.build(elements, onFirstPage=decorate, onLaterPages=decorate)
    return out
