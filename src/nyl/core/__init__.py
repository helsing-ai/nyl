# src/nyl/core/__init__.py
from .templating_processor import (
    ManifestsWithSource,
    OnLookupFailure,
    process_templates,
)

__all__ = [
    "ManifestsWithSource",
    "OnLookupFailure",
    "process_templates",
]
