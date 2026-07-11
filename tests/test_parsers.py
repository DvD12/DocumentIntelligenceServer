import pytest

from app.core.errors import ParseError
from app.ingestion.parsers import parse_document


def test_txt_single_section():
    doc = parse_document("notes.txt", b"Plain text body.")
    assert len(doc.sections) == 1
    assert doc.sections[0].heading_path == []
    assert doc.sections[0].page_start is None


def test_markdown_heading_stack():
    md = b"# Policy\nIntro text.\n\n## Limits\nCap is 10k.\n\n# Appendix\nEnd."
    doc = parse_document("p.md", md)
    paths = [s.heading_path for s in doc.sections]
    assert ["Policy"] in paths
    assert ["Policy", "Limits"] in paths
    assert ["Appendix"] in paths
    limits = next(s for s in doc.sections if s.heading_path == ["Policy", "Limits"])
    assert "Cap is 10k." in limits.text


def test_pdf_headings_and_pages(sample_pdf_bytes):
    doc = parse_document("policy.pdf", sample_pdf_bytes)
    headed = [s for s in doc.sections if s.heading_path]
    assert any(s.heading_path == ["1 Purpose"] and s.page_start == 1 for s in headed)
    assert any(s.heading_path == ["2 Client Tiers"] and s.page_start == 2 for s in headed)


def test_unsupported_extension():
    with pytest.raises(ParseError, match="Unsupported"):
        parse_document("sheet.xlsx", b"whatever")


def test_empty_content_rejected():
    with pytest.raises(ParseError, match="No extractable text"):
        parse_document("empty.txt", b"   ")
