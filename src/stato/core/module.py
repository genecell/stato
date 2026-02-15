"""Core types, schemas, and type inference for Stato modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModuleType(str, Enum):
    SKILL = "skill"
    PLAN = "plan"
    MEMORY = "memory"
    CONTEXT = "context"
    PROTOCOL = "protocol"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: Severity
    line: Optional[int] = None


@dataclass
class ValidationResult:
    success: bool
    module_type: Optional[ModuleType] = None
    class_name: Optional[str] = None
    hard_errors: list[Diagnostic] = field(default_factory=list)
    auto_corrections: list[Diagnostic] = field(default_factory=list)
    advice: list[Diagnostic] = field(default_factory=list)
    corrected_source: Optional[str] = None
    namespace: Optional[dict] = None


@dataclass
class GraftResult:
    success: bool
    has_conflict: bool = False
    conflicts: list[str] = field(default_factory=list)
    dependency_warnings: list[str] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    imported_modules: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Module schemas: field_name -> (expected_type, required)
# ---------------------------------------------------------------------------

SKILL_SCHEMA = {
    "required_fields": ["name"],
    "required_methods": ["run"],
    "field_types": {
        "name": str,
        "description": str,
        "version": str,
        "depends_on": list,
        "input_schema": dict,
        "output_schema": dict,
        "default_params": dict,
        "lessons_learned": str,
        "tags": list,
        "context_requires": list,
    },
}

PLAN_SCHEMA = {
    "required_fields": ["name", "objective", "steps"],
    "required_methods": [],
    "field_types": {
        "name": str,
        "objective": str,
        "steps": list,
        "version": str,
        "decision_log": str,
        "constraints": list,
        "created_by": str,
    },
}

MEMORY_SCHEMA = {
    "required_fields": ["phase"],
    "required_methods": [],
    "field_types": {
        "phase": str,
        "tasks": list,
        "known_issues": dict,
        "reflection": str,
        "error_history": list,
        "decisions": list,
        "metadata": dict,
        "last_updated": str,
    },
}

CONTEXT_SCHEMA = {
    "required_fields": ["project", "description"],
    "required_methods": [],
    "field_types": {
        "project": str,
        "description": str,
        "datasets": list,
        "environment": dict,
        "conventions": list,
        "tools": list,
        "pending_tasks": list,
        "completed_tasks": list,
        "team": list,
        "notes": str,
    },
}

PROTOCOL_SCHEMA = {
    "required_fields": ["name", "handoff_schema"],
    "required_methods": [],
    "field_types": {
        "name": str,
        "handoff_schema": dict,
        "description": str,
        "validation_rules": list,
        "error_handling": str,
    },
}

MODULE_SCHEMAS: dict[ModuleType, dict] = {
    ModuleType.SKILL: SKILL_SCHEMA,
    ModuleType.PLAN: PLAN_SCHEMA,
    ModuleType.MEMORY: MEMORY_SCHEMA,
    ModuleType.CONTEXT: CONTEXT_SCHEMA,
    ModuleType.PROTOCOL: PROTOCOL_SCHEMA,
}


def infer_module_type(
    class_name: str,
    field_names: set[str],
    method_names: set[str],
) -> tuple[ModuleType, bool]:
    """Infer module type from class name, fields, and methods.

    Returns (inferred_type, confident). confident=False triggers W006.
    """
    name_lower = class_name.lower()

    # Class name conventions
    if name_lower.endswith("context"):
        return ModuleType.CONTEXT, True
    if name_lower.endswith("state"):
        return ModuleType.MEMORY, True
    if name_lower.endswith("protocol"):
        return ModuleType.PROTOCOL, True

    # Field-based inference
    if "steps" in field_names and "objective" in field_names:
        return ModuleType.PLAN, True
    if "handoff_schema" in field_names:
        return ModuleType.PROTOCOL, True
    if "phase" in field_names and "run" not in method_names:
        return ModuleType.MEMORY, True
    if (
        "project" in field_names
        and "description" in field_names
        and "run" not in method_names
    ):
        return ModuleType.CONTEXT, True
    if "run" in method_names:
        return ModuleType.SKILL, True

    # Fallback — default to skill with low confidence
    return ModuleType.SKILL, False
