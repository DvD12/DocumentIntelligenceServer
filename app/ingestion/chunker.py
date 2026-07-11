import re

import tiktoken

from app.core.models import Chunk, ParsedDocument, ParsedSection

_ENC = tiktoken.get_encoding("cl100k_base")  # tokenizer family of text-embedding-3-*
MIN_CHUNK_TOKENS = 50
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _split_recursive(text: str, max_tokens: int) -> list[str]:
    """Split into pieces each <= max_tokens, preferring natural boundaries."""
    if count_tokens(text) <= max_tokens:
        return [text]
    for pattern in (_PARAGRAPH_RE, _SENTENCE_RE):
        parts = [p for p in pattern.split(text) if p.strip()]
        if len(parts) > 1:
            pieces: list[str] = []
            for part in parts:
                pieces.extend(_split_recursive(part, max_tokens))
            return pieces
    tokens = _ENC.encode(text)  # no separators left: hard cut
    return [_ENC.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)]


def _pack(pieces: list[str], target: int, overlap_tokens: int) -> list[str]:
    """Greedily pack pieces into chunks near `target` tokens, piece-level overlap."""
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for piece in pieces:
        piece_tokens = count_tokens(piece)
        if buffer and size + piece_tokens > target:
            chunks.append(" ".join(buffer))
            carried: list[str] = []
            carried_size = 0
            for prev in reversed(buffer):
                prev_tokens = count_tokens(prev)
                if carried_size + prev_tokens > overlap_tokens:
                    break
                carried.insert(0, prev)
                carried_size += prev_tokens
            buffer, size = carried, carried_size
        buffer.append(piece)
        size += piece_tokens
    if buffer:
        last = " ".join(buffer)
        if chunks and count_tokens(last) < MIN_CHUNK_TOKENS:
            chunks[-1] = chunks[-1] + " " + last
        else:
            chunks.append(last)
    return chunks


def _prefix(filename: str, heading_path: list[str]) -> str:
    if heading_path:
        return f"{filename} > {' > '.join(heading_path)} — "
    return f"{filename} — "


def chunk_document(
    parsed: ParsedDocument, filename: str, document_id: str,
    target_tokens: int, overlap: float,
) -> list[Chunk]:
    overlap_tokens = int(target_tokens * overlap)
    chunks: list[Chunk] = []
    index = 0
    for section in parsed.sections:
        text = section.text.strip()
        if not text:
            continue
        pieces = _split_recursive(text, target_tokens)
        for body in _pack(pieces, target_tokens, overlap_tokens):
            chunks.append(_make_chunk(section, filename, document_id, index, body))
            index += 1
    return chunks


def _make_chunk(
    section: ParsedSection, filename: str, document_id: str, index: int, body: str
) -> Chunk:
    return Chunk(
        document_id=document_id,
        chunk_index=index,
        text=body,
        prefixed_text=_prefix(filename, section.heading_path) + body,
        heading_path=section.heading_path,
        page_start=section.page_start,
        page_end=section.page_end,
        token_count=count_tokens(body),
    )
