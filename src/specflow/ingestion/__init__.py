"""BRD/PRD ingestion and processing for SpecFlow."""

from specflow.ingestion.ingest import Ingestor
from specflow.ingestion.validator import SpecValidator

__all__ = ["Ingestor", "SpecValidator"]
