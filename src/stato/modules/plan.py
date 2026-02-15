"""PlanModule schema helpers, computed properties, and template reset."""
from __future__ import annotations

import ast
import re
from typing import Optional

from stato.core.module import Diagnostic, Severity

ALLOWED_STATUSES = {"pending", "running", "complete", "failed", "blocked"}


def validate_plan(namespace: dict, class_name: str) -> list[Diagnostic]:
    """Plan-specific validation beyond schema checks."""
    # Handled inline in compiler Pass 7 (_validate_plan_semantics)
    return []


class PlanHelpers:
    """Computed properties for a plan module."""

    @staticmethod
    def current_step(steps: list[dict]) -> Optional[dict]:
        """Return the step with status 'running', or None."""
        for s in steps:
            if s.get("status") == "running":
                return s
        return None

    @staticmethod
    def next_step(steps: list[dict]) -> Optional[dict]:
        """Return the first 'pending' step whose dependencies are all 'complete'."""
        complete_ids = {s["id"] for s in steps if s.get("status") == "complete"}
        for s in steps:
            if s.get("status") != "pending":
                continue
            deps = s.get("depends_on", [])
            if all(d in complete_ids for d in deps):
                return s
        return None

    @staticmethod
    def progress(steps: list[dict]) -> tuple[int, int]:
        """Return (completed_count, total_count)."""
        complete = sum(1 for s in steps if s.get("status") == "complete")
        return (complete, len(steps))

    @staticmethod
    def is_complete(steps: list[dict]) -> bool:
        """True if all steps are 'complete'."""
        return all(s.get("status") == "complete" for s in steps)


def reset_plan_for_template(source: str) -> str:
    """Template mode: all step statuses -> 'pending', clear outputs.

    Uses AST parse + modify + ast.unparse() for reliability.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_node = node
            break
    if class_node is None:
        return source

    # Find the 'steps' assignment
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "steps":
                _reset_steps_node(node.value)

    return ast.unparse(tree)


def _reset_steps_node(node: ast.expr) -> None:
    """Walk a steps list AST node and reset statuses + clear outputs."""
    if not isinstance(node, ast.List):
        return

    for elt in node.elts:
        if not isinstance(elt, ast.Dict):
            continue

        keys_to_remove = []
        for i, (key, value) in enumerate(zip(elt.keys, elt.values)):
            if isinstance(key, ast.Constant):
                if key.value == "status":
                    # Reset to "pending"
                    elt.values[i] = ast.Constant(value="pending")
                elif key.value == "output":
                    keys_to_remove.append(i)

        # Remove output keys in reverse order
        for i in sorted(keys_to_remove, reverse=True):
            elt.keys.pop(i)
            elt.values.pop(i)
