"""SkillModule schema helpers and template reset."""
from __future__ import annotations

from stato.core.module import Diagnostic, Severity


def validate_skill(namespace: dict, class_name: str) -> list[Diagnostic]:
    """Skill-specific validation beyond schema checks."""
    # Handled inline in compiler Pass 7 (_validate_skill_semantics)
    return []


def reset_skill_for_template(source: str) -> str:
    """Template mode for skills: keep everything.

    Skills ARE the expertise — lessons_learned, default_params all stay.
    """
    return source
