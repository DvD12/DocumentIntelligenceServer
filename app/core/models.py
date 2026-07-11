from datetime import datetime

from pydantic import BaseModel, Field


class ParsedSection(BaseModel):
    heading_path: list[str] = Field(default_factory=list)
    text: str
    page_start: int | None = None
    page_end: int | None = None


class ParsedDocument(BaseModel):
    sections: list[ParsedSection]


class Chunk(BaseModel):
    document_id: str
    chunk_index: int
    text: str
    prefixed_text: str
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    token_count: int


class DocumentMeta(BaseModel):
    id: str
    filename: str
    content_hash: str
    media_type: str
    size_bytes: int
    chunk_count: int
    tags: list[str] = Field(default_factory=list)
    uploaded_at: datetime
    updated_at: datetime
