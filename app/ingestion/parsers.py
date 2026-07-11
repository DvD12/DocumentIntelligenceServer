import io
import re
from statistics import median

import pdfplumber

from app.core.errors import ParseError
from app.core.models import ParsedDocument, ParsedSection

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PDF_HEADING_SIZE_RATIO = 1.15
_PDF_HEADING_MAX_CHARS = 80


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        doc = _parse_pdf(data)
    elif lower.endswith((".md", ".markdown")):
        doc = _parse_markdown(_decode(data))
    elif lower.endswith(".txt"):
        doc = ParsedDocument(sections=[ParsedSection(text=_decode(data))])
    else:
        raise ParseError(f"Unsupported file type: '{filename}'. Supported: .pdf, .txt, .md")
    if not any(s.text.strip() for s in doc.sections):
        raise ParseError(f"No extractable text in '{filename}'.")
    return doc


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _parse_markdown(text: str) -> ParsedDocument:
    sections: list[ParsedSection] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(ParsedSection(heading_path=[t for _, t in stack], text=body))
        buffer.clear()

    for line in text.splitlines():
        m = _MD_HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2)))
        else:
            buffer.append(line)
    flush()
    return ParsedDocument(sections=sections)


def _parse_pdf(data: bytes) -> ParsedDocument:
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfplumber raises various types on corrupt input
        raise ParseError(f"Could not open PDF: {exc}") from exc

    with pdf:
        page_lines: list[tuple[int, str, float]] = []  # (page_no, text, median char size)
        for page_no, page in enumerate(pdf.pages, start=1):
            for line in page.extract_text_lines():
                sizes = [c["size"] for c in line["chars"]]
                if line["text"].strip() and sizes:
                    page_lines.append((page_no, line["text"].strip(), median(sizes)))

    if not page_lines:
        return ParsedDocument(sections=[])
    body_size = median(size for _, _, size in page_lines)

    sections: list[ParsedSection] = []
    heading: list[str] = []
    buffer: list[str] = []
    start_page = end_page = page_lines[0][0]

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(ParsedSection(
                heading_path=list(heading), text=body,
                page_start=start_page, page_end=end_page,
            ))
        buffer.clear()

    for page_no, text, size in page_lines:
        is_heading = (
            size > body_size * _PDF_HEADING_SIZE_RATIO
            and len(text) < _PDF_HEADING_MAX_CHARS
            and not text.endswith(".")
        )
        if is_heading:
            flush()
            heading = [text]
            start_page = page_no
        else:
            if not buffer:
                start_page = page_no
            buffer.append(text)
        end_page = page_no
    flush()
    return ParsedDocument(sections=sections)
