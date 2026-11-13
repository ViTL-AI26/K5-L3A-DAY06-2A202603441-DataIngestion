"""Read and normalize source data."""

import re
import json
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraphs."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    selected_pages: list[int] | None = None,
    extra_metadata: dict | None = None,
) -> list[DocumentPage]:
    """Extract selected PDF pages and preserve physical page numbering."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {path}")

    reader = PdfReader(str(path))
    total_pages = len(reader.pages)

    pages_to_load = (
        selected_pages
        if selected_pages is not None
        else list(range(1, total_pages + 1))
    )

    invalid_pages = [
        page for page in pages_to_load
        if not isinstance(page, int) or page < 1 or page > total_pages
    ]

    if invalid_pages:
        raise ValueError(
            f"Invalid PDF page numbers: {invalid_pages}. "
            f"PDF contains {total_pages} pages."
        )

    documents = []

    for page_number in pages_to_load:
        pdf_page = reader.pages[page_number - 1]
        raw_text = pdf_page.extract_text() or ""
        text = normalize_text(raw_text)

        metadata = {
            "is_empty": not bool(text),
            "file_name": path.name,
            "file_type": "pdf",
        }

        if extra_metadata:
            metadata.update(extra_metadata)

        documents.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                text=text,
                metadata=metadata,
            )
        )
    return documents

def load_corpus(
    manifest_path: Path,
) -> list[DocumentPage]:
    """Load selected PDF pages defined in a corpus manifest."""
    manifest_path = Path(manifest_path)

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}"
        )

    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)

    documents = []

    for source_info in manifest["sources"]:
        source_path = Path(source_info["source_path"])

        metadata = {
            "source_id": source_info["source_id"],
            "title": source_info["title"],
            "license": source_info["license"],
            "year": source_info["year"],
            "topic": "Generative AI and AI in Higher Education",
        }

        documents.extend(
            load_pdf(
                path=source_path,
                document_id=source_info["source_id"],
                source=source_info["source_id"],
                selected_pages=source_info["pages"],
                extra_metadata=metadata,
            )
        )

    return documents
