from app.core.models import ParsedDocument, ParsedSection
from app.ingestion.chunker import MIN_CHUNK_TOKENS, chunk_document, count_tokens


def _doc(text: str, heading: list[str] | None = None) -> ParsedDocument:
    return ParsedDocument(
        sections=[ParsedSection(heading_path=heading or [], text=text, page_start=1, page_end=2)]
    )


def _long_text(sentences: int = 200) -> str:
    return " ".join(
        f"Sentence number {i} talks about the compliance policy in some detail."
        for i in range(sentences)
    )


def test_short_section_is_single_chunk():
    chunks = chunk_document(_doc("Hello world."), "a.txt", "d1", 450, 0.15)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "Hello world."


def test_long_section_splits_within_budget():
    chunks = chunk_document(_doc(_long_text()), "a.txt", "d1", 450, 0.15)
    assert len(chunks) > 1
    assert all(count_tokens(c.text) <= int(450 * 1.2) for c in chunks)


def test_overlap_repeats_trailing_sentence():
    chunks = chunk_document(_doc(_long_text()), "a.txt", "d1", 450, 0.15)
    last_sentence = chunks[0].text.split(". ")[-2]
    assert last_sentence in chunks[1].text


def test_no_tiny_trailing_chunk():
    chunks = chunk_document(_doc(_long_text()), "a.txt", "d1", 450, 0.15)
    assert count_tokens(chunks[-1].text) >= MIN_CHUNK_TOKENS


def test_prefix_contains_filename_and_headings():
    doc = ParsedDocument(sections=[
        ParsedSection(heading_path=["3 Client Tiers", "3.2 Limits"], text="Tier-2 caps apply.")
    ])
    chunks = chunk_document(doc, "aml-policy.pdf", "d1", 450, 0.15)
    assert chunks[0].prefixed_text == (
        "aml-policy.pdf > 3 Client Tiers > 3.2 Limits — Tier-2 caps apply."
    )
    assert chunks[0].text == "Tier-2 caps apply."


def test_chunk_index_global_across_sections():
    doc = ParsedDocument(sections=[
        ParsedSection(heading_path=["A"], text="First section."),
        ParsedSection(heading_path=["B"], text="Second section."),
    ])
    chunks = chunk_document(doc, "a.md", "d1", 450, 0.15)
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert chunks[1].heading_path == ["B"]
