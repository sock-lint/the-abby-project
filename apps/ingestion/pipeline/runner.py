"""High-level entry point for running the ingestion pipeline."""
from __future__ import annotations

from .base import IngestionItem
from .detect import route_source
from .pipeline import default_pipeline


def run_ingestion(source_type: str, source_url: str | None, file_field) -> IngestionItem:
    """Route to the right ingestor, build the default pipeline, and run it."""
    ingestor = route_source(source_type, source_url, file_field)
    pipeline = default_pipeline(ingestor)
    seed = IngestionItem(source_type=source_type, source_url=source_url)
    return pipeline.run(seed, context={"ingestor": ingestor})
