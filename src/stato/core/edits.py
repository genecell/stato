"""Targeted module edits — AST parse-modify-unparse (never executes code).

Small, surgical edits so an agent (or the MCP tools) can change one thing
without regenerating a whole module. Same reliable pattern as
`modules.plan.reset_plan_for_template`: parse, mutate the AST, `ast.unparse`.
Callers should re-validate the returned source before persisting.
"""
from __future__ import annotations

import ast

from stato.core.astload import load_class, safe_parse


class EditError(ValueError):
    """Raised when the edit target can't be found."""


def _first_class(tree: ast.Module) -> ast.ClassDef | None:
    return next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)


def _find_assign(class_node: ast.ClassDef, name: str) -> ast.Assign | None:
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return node
    return None


def set_plan_step(source: str, step_id: int, status: str | None = None,
                  output: str | None = None) -> str:
    """Update a plan step's status and/or output. Raises if step_id is absent."""
    try:
        tree = safe_parse(source)
    except SyntaxError as e:
        raise EditError(f"source is not valid Python: {e}") from e

    class_node = _first_class(tree)
    if class_node is None:
        raise EditError("no class definition found")
    steps_assign = _find_assign(class_node, "steps")
    if steps_assign is None or not isinstance(steps_assign.value, ast.List):
        raise EditError("no `steps` list found")

    target_dict = None
    for elt in steps_assign.value.elts:
        if not isinstance(elt, ast.Dict):
            continue
        for k, v in zip(elt.keys, elt.values, strict=False):
            if isinstance(k, ast.Constant) and k.value == "id" \
                    and isinstance(v, ast.Constant) and v.value == step_id:
                target_dict = elt
                break
        if target_dict is not None:
            break

    if target_dict is None:
        raise EditError(f"no step with id {step_id}")

    def _set_key(d: ast.Dict, key: str, value):
        for i, k in enumerate(d.keys):
            if isinstance(k, ast.Constant) and k.value == key:
                d.values[i] = ast.Constant(value=value)
                return
        d.keys.append(ast.Constant(value=key))
        d.values.append(ast.Constant(value=value))

    if status is not None:
        _set_key(target_dict, "status", status)
    if output is not None:
        _set_key(target_dict, "output", output)

    return ast.unparse(tree) + "\n"


def migrate_lessons(source: str) -> str:
    """Convert prose `lessons_learned` bullets into a structured `lessons` list.

    Each `- ` bullet becomes {"recommendation": "<text>"}. Leaves the prose
    field in place (non-destructive). Returns source unchanged if there's no
    prose to migrate or it already has structured lessons.
    """
    cls = load_class(source)
    if cls is None:
        return source
    if isinstance(getattr(cls, "lessons", None), list) and cls.lessons:
        return source  # already structured
    prose = getattr(cls, "lessons_learned", "") or ""
    if not prose.strip():
        return source

    # Reuse the summarizer's bullet splitter for consistency.
    from stato.core.summarize import _extract_lessons
    bullets = _extract_lessons(cls)
    if not bullets:
        return source
    entries = [{"recommendation": b.text} for b in bullets]

    try:
        tree = safe_parse(source)
    except SyntaxError:
        return source
    class_node = _first_class(tree)
    if class_node is None:
        return source
    new_assign = ast.Assign(
        targets=[ast.Name(id="lessons", ctx=ast.Store())],
        value=ast.parse(repr(entries), mode="eval").body,
    )
    # insert after lessons_learned if present, else after docstring
    idx = None
    for i, node in enumerate(class_node.body):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "lessons_learned" for t in node.targets
        ):
            idx = i + 1
            break
    if idx is None:
        idx = 1 if (class_node.body and isinstance(class_node.body[0], ast.Expr)) else 0
    class_node.body.insert(idx, new_assign)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def stamp_updated_at(source: str, when: str) -> str:
    """Set/replace `updated_at = "<when>"` on the class.

    Best-effort: returns the source unchanged if it can't be parsed.
    """
    try:
        tree = safe_parse(source)
    except SyntaxError:
        return source
    class_node = _first_class(tree)
    if class_node is None:
        return source
    assign = _find_assign(class_node, "updated_at")
    if assign is not None:
        assign.value = ast.Constant(value=when)
    else:
        new_assign = ast.Assign(
            targets=[ast.Name(id="updated_at", ctx=ast.Store())],
            value=ast.Constant(value=when),
        )
        insert_at = 1 if (class_node.body and isinstance(class_node.body[0], ast.Expr)
                          and isinstance(getattr(class_node.body[0], "value", None), ast.Constant)
                          and isinstance(class_node.body[0].value.value, str)) else 0
        class_node.body.insert(insert_at, new_assign)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def append_lesson(source: str, lesson: str) -> str:
    """Append a bullet to `lessons_learned`, creating the field if missing."""
    try:
        tree = safe_parse(source)
    except SyntaxError as e:
        raise EditError(f"source is not valid Python: {e}") from e

    class_node = _first_class(tree)
    if class_node is None:
        raise EditError("no class definition found")

    bullet = lesson.strip()
    assign = _find_assign(class_node, "lessons_learned")
    if assign is not None and isinstance(assign.value, ast.Constant) \
            and isinstance(assign.value.value, str):
        existing = assign.value.value.rstrip()
        newline = "\n" if existing and not existing.endswith("\n") else ""
        assign.value = ast.Constant(value=f"{existing}{newline}\n    - {bullet}\n    ")
    else:
        # Insert a new lessons_learned assignment after the docstring (or at top).
        new_assign = ast.Assign(
            targets=[ast.Name(id="lessons_learned", ctx=ast.Store())],
            value=ast.Constant(value=f"\n    - {bullet}\n    "),
        )
        insert_at = 1 if (class_node.body and isinstance(class_node.body[0], ast.Expr)
                          and isinstance(getattr(class_node.body[0], "value", None), ast.Constant)
                          and isinstance(class_node.body[0].value.value, str)) else 0
        class_node.body.insert(insert_at, new_assign)

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"
