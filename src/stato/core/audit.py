"""Audit — quality scoring for stato modules.

Gives a 0-10 score plus concrete, actionable gaps. Deterministic and AST-only
(never executes module code). `today` is injectable so stale-date checks are
testable. Addresses the "crystallization quality varies" weakness and can gate
what gets published to the registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from stato.core.astload import load_class
from stato.core.compiler import validate
from stato.core.module import ModuleType


@dataclass
class Check:
    key: str
    passed: bool
    weight: float
    suggestion: str  # shown only when failed


@dataclass
class AuditReport:
    path: str
    module_type: str | None
    score: float                       # 0-10
    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "module_type": self.module_type,
            "score": round(self.score, 1),
            "checks": [
                {"key": c.key, "passed": c.passed, "weight": c.weight,
                 "suggestion": None if c.passed else c.suggestion}
                for c in self.checks
            ],
        }


def _parse_iso_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def audit_module(source: str, path: str = "<module>", today: date | None = None) -> AuditReport:
    """Score one module 0-10 with per-check detail."""
    today = today or date.today()
    result = validate(source)
    cls = load_class(source)
    mtype = result.module_type

    checks: list[Check] = []

    def add(key, passed, weight, suggestion):
        checks.append(Check(key, bool(passed), weight, suggestion))

    has = lambda attr: cls is not None and bool(getattr(cls, attr, None))  # noqa: E731

    # Universal checks
    add("docstring", bool(cls is not None and (cls.__doc__ or "").strip()), 1.0,
        "Add a one-line docstring describing the module's purpose.")
    add("provenance", has("source") or has("updated_at"), 1.0,
        "Add `source` or `updated_at` so freshness is visible.")

    if mtype == ModuleType.SKILL:
        structured = getattr(cls, "lessons", None) if cls else None
        add("lessons", has("lessons_learned") or bool(structured), 2.0,
            "Capture lessons_learned (or structured `lessons`) — the WHY, not just WHAT.")
        add("params_documented", has("default_params"), 1.0,
            "Document default_params with the values you actually used.")
        add("version", has("version"), 1.0,
            "Add a semantic `version` so the skill can evolve.")
        add("confidence", isinstance(getattr(cls, "confidence", None), (int, float))
            and not isinstance(getattr(cls, "confidence", None), bool), 1.0,
            "Set `confidence` (0-1) so consumers know how much to trust this.")
        add("run_typed", _run_has_hints(cls), 0.5,
            "Add type hints to run() for clearer contracts.")
        # Stale-knowledge flag: any review_by date in the past
        stale = _stale_reviews(structured, today)
        add("no_stale_lessons", not stale, 1.0,
            f"Lessons overdue for review: {', '.join(stale)}. Re-verify or update review_by.")

    elif mtype == ModuleType.PLAN:
        add("decision_log", has("decision_log"), 2.0,
            "Add a decision_log capturing key decisions and rationale.")
        steps = getattr(cls, "steps", None) if cls else None
        add("completed_have_output", _completed_have_output(steps), 1.5,
            "Give completed steps an `output` so the record is useful later.")

    elif mtype == ModuleType.MEMORY:
        add("reflection", has("reflection"), 2.0,
            "Add a reflection: where things stand and what's next.")
        add("known_issues", has("known_issues"), 1.0,
            "Record known_issues so they aren't rediscovered.")

    elif mtype == ModuleType.CONTEXT:
        add("conventions", has("conventions"), 1.5,
            "List the project conventions an agent should follow.")
        add("environment", has("environment"), 1.0,
            "Record the environment (packages/versions) for reproducibility.")

    total_w = sum(c.weight for c in checks) or 1.0
    passed_w = sum(c.weight for c in checks if c.passed)
    score = 10.0 * passed_w / total_w
    return AuditReport(path=path, module_type=(mtype.value if mtype else None),
                       score=score, checks=checks)


def audit_directory(stato_dir, today: date | None = None) -> tuple[list[AuditReport], float]:
    """Audit every module in .stato/. Returns (reports, aggregate_score)."""
    from pathlib import Path

    stato_dir = Path(stato_dir)
    reports = []
    for py in sorted(stato_dir.rglob("*.py")):
        if ".history" in py.parts or py.name.startswith("__"):
            continue
        rel = py.relative_to(stato_dir)
        reports.append(audit_module(py.read_text(), str(rel), today=today))
    agg = sum(r.score for r in reports) / len(reports) if reports else 0.0
    return reports, agg


def _run_has_hints(cls) -> bool:
    run = getattr(cls, "run", None) if cls else None
    return bool(run and getattr(run, "__annotations__", {}))


def _completed_have_output(steps) -> bool:
    if not isinstance(steps, list):
        return False
    completed = [s for s in steps if isinstance(s, dict) and s.get("status") == "complete"]
    if not completed:
        return True  # nothing completed yet — not a gap
    return all(s.get("output") for s in completed)


def _stale_reviews(structured, today: date) -> list[str]:
    stale = []
    if isinstance(structured, list):
        for entry in structured:
            if isinstance(entry, dict):
                d = _parse_iso_date(entry.get("review_by"))
                if d is not None and d < today:
                    stale.append(entry.get("review_by"))
    return stale
