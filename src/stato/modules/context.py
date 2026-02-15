"""ContextModule schema helpers and template reset."""
from __future__ import annotations

from stato.core.module import Diagnostic, Severity


def validate_context(namespace: dict, class_name: str) -> list[Diagnostic]:
    """Context-specific validation beyond schema checks."""
    return []


def reset_context_for_template(source: str) -> str:
    """Template mode: keep everything (conventions, tools are reusable)."""
    return source
