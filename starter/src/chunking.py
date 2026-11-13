"""Implement fixed-size and structure-aware chunking."""

import hashlib
import re

from .models import Chunk, DocumentPage


def _make_chunk(
    page: DocumentPage,
    text: str,
    method: str,
    index: int,
) -> Chunk:
    """Create a chunk with a deterministic ID and source metadata."""

    text = text.strip()

    raw_id = (
        f"{page.document_id}|{page.page}|"
        f"{method}|{index}|{text}"
    )

    chunk_id = hashlib.sha256(
        raw_id.encode("utf-8")
    ).hexdigest()

    metadata = dict(page.metadata)
    metadata.update({
        "chunking_method": method,
        "chunk_index": index,
    })

    return Chunk(
        chunk_id=chunk_id,
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=metadata,
    )


def fixed_size(
    page: DocumentPage,
    size: int,
    overlap: int
) -> list[Chunk]:
    """Split text into overlapping character windows."""

    if size <= 0:
        raise ValueError("size must be greater than zero")

    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")

    text = page.text.strip()

    if not text:
        return []

    chunks = []
    step = size - overlap

    for index, start in enumerate(range(0, len(text), step)):
        content = text[start:start + size].strip()

        if content:
            chunks.append(
                _make_chunk(
                    page,
                    content,
                    "fixed_size",
                    index,
                )
            )

        if start + size >= len(text):
            break

    return chunks


def _split_long_paragraph(
    paragraph: str,
    max_size: int
) -> list[str]:
    """Split oversized paragraphs without exceeding max_size."""

    parts = []

    while len(paragraph) > max_size:
        split_at = paragraph.rfind(" ", 0, max_size + 1)

        if split_at <= 0:
            split_at = max_size

        parts.append(paragraph[:split_at].strip())
        paragraph = paragraph[split_at:].strip()

    if paragraph:
        parts.append(paragraph)

    return parts


def by_paragraph(
    page: DocumentPage,
    max_size: int
) -> list[Chunk]:
    """Group paragraphs and split oversized paragraphs."""

    if max_size <= 0:
        raise ValueError("max_size must be greater than zero")

    if not page.text.strip():
        return []

    paragraphs = re.split(
        r"\n\s*\n",
        page.text.strip()
    )

    units = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        units.extend(
            _split_long_paragraph(paragraph, max_size)
        )

    chunks = []
    current_parts = []
    current_length = 0

    for paragraph in units:
        separator_length = 2 if current_parts else 0
        new_length = current_length + separator_length + len(paragraph)

        if current_parts and new_length > max_size:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_length = 0

        current_parts.append(paragraph)
        current_length += (
            (2 if len(current_parts) > 1 else 0)
            + len(paragraph)
        )

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return [
        _make_chunk(page, text, "by_paragraph", index)
        for index, text in enumerate(chunks)
    ]
