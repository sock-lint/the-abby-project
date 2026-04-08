"""Route a source (URL or uploaded file) to the right ingestor."""
from __future__ import annotations

from .base import BaseIngestor, IngestionResult
from .generic_url import GenericUrlIngestor
from .instructables import InstructablesIngestor
from .pdf import PdfIngestor


def route_source(source_type: str, source_url: str | None, file_field) -> BaseIngestor:
    """Return the ingestor for this source.

    ``source_type`` is the hint from the API payload (``instructables``,
    ``url``, ``pdf``). URL values are auto-upgraded to Instructables when we
    recognise the domain.
    """
    if source_type == "pdf" or (file_field and not source_url):
        if file_field is None:
            raise ValueError("PDF source requires a file upload")
        return PdfIngestor(file_field)

    if not source_url:
        raise ValueError("source_url required for URL ingestion")

    if source_type == "instructables" or "instructables.com" in source_url:
        return InstructablesIngestor(source_url)

    return GenericUrlIngestor(source_url)


def run_ingestion(source_type: str, source_url: str | None, file_field) -> IngestionResult:
    ingestor = route_source(source_type, source_url, file_field)
    return ingestor.ingest()
