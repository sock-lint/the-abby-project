from .base import (
    BaseIngestor, IngestionItem, IngestionResult, MaterialDraft, MilestoneDraft,
    ResourceDraft, StepDraft,
)
from .detect import route_source
from .pipeline import NormalizeStage, ParseStage, Pipeline, StageSkip, default_pipeline
from .runner import run_ingestion

__all__ = [
    "BaseIngestor",
    "IngestionItem",
    "IngestionResult",
    "MaterialDraft",
    "MilestoneDraft",  # alias of StepDraft for backwards compat
    "NormalizeStage",
    "ParseStage",
    "Pipeline",
    "ResourceDraft",
    "StageSkip",
    "StepDraft",
    "default_pipeline",
    "route_source",
    "run_ingestion",
]
