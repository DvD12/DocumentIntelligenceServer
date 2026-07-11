import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Two-page PDF: 18pt headings, 10pt body — exercises the heading heuristic."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 780, "1 Purpose")
    c.setFont("Helvetica", 10)
    for i in range(3):
        c.drawString(72, 750 - 14 * i, f"This policy explains the purpose, line {i}")
    c.showPage()
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 780, "2 Client Tiers")
    c.setFont("Helvetica", 10)
    for i in range(3):
        c.drawString(72, 750 - 14 * i, f"Tier rules and transfer caps, line {i}")
    c.showPage()
    c.save()
    return buf.getvalue()
