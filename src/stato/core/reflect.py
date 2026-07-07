"""Reflect — surface evidence of dead-ends from a module's edit history.

stato already records the raw material for reflection: every validated write
leaves a timestamped backup in .stato/.history/. The field-level value sequence
across those backups is empirical evidence of how expertise evolved — and a
value that changes and then *reverts* (e.g. a parameter 20 -> 25 -> 20) is a
dead-end the model can't have forgotten, because it's in the trail.

`reflect()` surfaces those **candidate lessons** (reversions + churn). stato
provides the evidence; the model distills it into a lesson (via append_lesson).
Deterministic, AST-only, no model call. Directly counters the "negative results
bias" — failures the agent might not think to record are visible in its own
history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from stato.core.astload import extract_field_values


@dataclass
class ReflectionCandidate:
    module: str          # rel path, e.g. skills/qc.py
    field: str           # field or default_params.<key>
    signal: str          # "reversion" | "churn"
    evidence: str        # "20 -> 25 -> 20 across 3 revisions"
    suggestion: str

    def to_dict(self) -> dict:
        return vars(self)


@dataclass
class ReflectionReport:
    candidates: list[ReflectionCandidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"candidates": [c.to_dict() for c in self.candidates]}

    def render(self) -> str:
        if not self.candidates:
            return ("No reversions or churn found in .stato/.history/ — nothing "
                    "to reflect on yet.")
        lines = ["# Reflection — candidate lessons from your edit history",
                 "(stato surfaces the evidence; you decide what to record as a lesson)"]
        by_module: dict[str, list[ReflectionCandidate]] = {}
        for c in self.candidates:
            by_module.setdefault(c.module, []).append(c)
        for module, cands in by_module.items():
            lines.append(f"\n## {module}")
            for c in cands:
                tag = "reverted" if c.signal == "reversion" else "churned"
                lines.append(f"- `{c.field}` {tag}: {c.evidence}")
                lines.append(f"  → {c.suggestion}")
        return "\n".join(lines)


def _snapshots(stato_dir: Path, rel_path: str) -> list[str]:
    """All source snapshots of a module, oldest -> newest (history + current)."""
    stem = Path(rel_path).stem
    history_dir = stato_dir / ".history"
    sources: list[str] = []
    if history_dir.exists():
        # Sort by the timestamp embedded in the filename (ISO -> lexical order);
        # mtime can tie on fast successive writes.
        backups = sorted(history_dir.glob(f"{stem}.*.py"), key=lambda p: p.name)
        sources.extend(b.read_text() for b in backups)
    current = stato_dir / rel_path
    if current.exists():
        sources.append(current.read_text())
    return sources


# Narrative fields churn by nature — reversion there isn't a "dead-end" signal.
_NARRATIVE = {"reflection", "lessons_learned", "notes", "decision_log",
              "objective", "description", "created_by"}


def _is_signal_scalar(v) -> bool:
    if isinstance(v, bool) or isinstance(v, (int, float)) or v is None:
        return True
    # short strings only (versions, names, statuses) — skip prose
    return isinstance(v, str) and len(v) <= 60


def _flatten(fields: dict) -> dict:
    """Signal-bearing scalars + one level into dicts (default_params.<key>).

    Skips narrative/prose fields where churn is expected and uninformative.
    """
    flat: dict = {}
    for k, v in fields.items():
        if k in _NARRATIVE:
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                if _is_signal_scalar(vv):
                    flat[f"{k}.{kk}"] = vv
        elif _is_signal_scalar(v):
            flat[k] = v
    return flat


def _analyze(values: list) -> tuple[list, int, bool]:
    """Collapse consecutive dups → (collapsed, churn, reverted)."""
    collapsed: list = []
    for v in values:
        if not collapsed or collapsed[-1] != v:
            collapsed.append(v)
    churn = max(0, len(collapsed) - 1)
    # reversion: a value reappears after having changed away (non-consecutive dup)
    seen = [repr(v) for v in collapsed]
    reverted = len(seen) != len(set(seen))
    return collapsed, churn, reverted


def reflect(stato_dir, min_churn: int = 3) -> ReflectionReport:
    """Find reversions/churn across module history. Deterministic, no model call."""
    from stato.core.composer import _discover_modules

    stato_dir = Path(stato_dir)
    candidates: list[ReflectionCandidate] = []

    for mod in _discover_modules(stato_dir):
        rel = str(mod["rel_path"])
        snaps = _snapshots(stato_dir, rel)
        if len(snaps) < 2:
            continue  # no history to reflect on

        # Build per-field value sequences across snapshots.
        sequences: dict[str, list] = {}
        for src in snaps:
            flat = _flatten(extract_field_values(src))
            for f, v in flat.items():
                sequences.setdefault(f, []).append(v)

        for f, values in sequences.items():
            # only consider fields present in most snapshots (changed at all)
            _collapsed, churn, reverted = _analyze(values)
            if churn == 0:
                continue
            evidence = (" → ".join(repr(v) for v in _collapsed)
                        + f" across {len(values)} revisions")
            if reverted:
                candidates.append(ReflectionCandidate(
                    module=rel, field=f, signal="reversion", evidence=evidence,
                    suggestion=f"a value was tried and reverted — record why in "
                               f"{Path(rel).stem}'s lessons (what failed about the "
                               "intermediate value).",
                ))
            elif churn >= min_churn:
                candidates.append(ReflectionCandidate(
                    module=rel, field=f, signal="churn", evidence=evidence,
                    suggestion=f"this changed {churn}× — if it's unstable/context-"
                               "dependent, capture the rule in a lesson.",
                ))

    # reversions first (stronger signal), then churn
    candidates.sort(key=lambda c: (c.signal != "reversion", c.module, c.field))
    return ReflectionReport(candidates=candidates)
