"""Stato compiler — 7-pass validation pipeline.

Public API:
    validate(source, expected_type=None) -> ValidationResult
    decompile(source) -> str
    compile_from_markdown(markdown) -> (str, ValidationResult)
"""
from __future__ import annotations

import ast
import re
import textwrap

from stato.core.astload import safe_parse
from stato.core.module import (
    MODULE_SCHEMAS,
    Diagnostic,
    ModuleType,
    Severity,
    ValidationResult,
    infer_module_type,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(
    source: str,
    expected_type: str | None = None,
    strict: bool = False,
    suppress: list[str] | None = None,
    error_codes: list[str] | None = None,
) -> ValidationResult:
    """Run the 7-pass validation pipeline on Python source code.

    strict: promote auto-correction WARNINGS to hard errors (advice/info stays
        advisory — style lints shouldn't fail a correctness gate).
    suppress: diagnostic codes (e.g. ["I006"]) to drop from the result.
    error_codes: specific codes to promote to hard errors (granular strictness),
        e.g. ["I006"] to require type hints without promoting everything.
    """
    result = _validate_inner(source, expected_type)
    return _apply_policy(
        result, strict=strict, suppress=suppress or [], error_codes=error_codes or [],
    )


def _validate_inner(source: str, expected_type: str | None = None) -> ValidationResult:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []
    advice: list[Diagnostic] = []

    # Pass 1: Syntax
    tree = _pass_syntax(source, errors, advice)
    if tree is None:
        return _build_result(errors, warnings, advice, success=False)

    # Pass 2: Structure
    class_node, class_name, has_docstring = _pass_structure(tree, errors, warnings)
    if class_node is None:
        return _build_result(errors, warnings, advice, success=False)

    # Explicit type declaration: __stato_type__ = "skill" overrides inference
    declared_type = _extract_declared_type(class_node, errors, warnings, expected_type)
    if errors:
        return _build_result(
            errors, warnings, advice, success=False, class_name=class_name,
        )
    if declared_type is not None:
        expected_type = declared_type

    # Pass 3: Type Inference
    field_names, method_names = _extract_members(class_node)
    module_type = _pass_type_infer(
        class_name, field_names, method_names, expected_type, warnings, advice,
        has_docstring,
    )

    # Pass 4: Schema Check
    _pass_schema(module_type, field_names, method_names, errors)
    if errors:
        return _build_result(
            errors, warnings, advice, success=False,
            module_type=module_type, class_name=class_name,
        )

    # Pass 5: Type Check + Auto-corrections
    corrected_source = _pass_type_check(
        source, class_node, module_type, errors, warnings,
    )

    if errors:
        return _build_result(
            errors, warnings, advice, success=False,
            module_type=module_type, class_name=class_name,
        )

    # Pass 6: Materialize (AST-only — module code is never executed)
    exec_source = corrected_source or source
    namespace = _pass_materialize(exec_source, class_name, module_type, errors, advice)
    if errors:
        return _build_result(
            errors, warnings, advice, success=False,
            module_type=module_type, class_name=class_name,
        )

    # Pass 7: Semantic (module-specific)
    _pass_semantic(namespace, class_name, module_type, errors, warnings, advice)

    has_errors = bool(errors)
    return _build_result(
        errors, warnings, advice,
        success=not has_errors,
        module_type=module_type,
        class_name=class_name,
        corrected_source=corrected_source,
        namespace=namespace,
    )


def decompile(source: str) -> str:
    """Convert Python module source to readable markdown."""
    try:
        tree = safe_parse(source)
    except SyntaxError:
        return f"# Invalid Module\n\nSource has syntax errors.\n\n## Source\n\n```python\n{source}\n```\n"

    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_node = node
            break

    if class_node is None:
        return f"# No Class Found\n\n## Source\n\n```python\n{source}\n```\n"

    lines = [f"# {class_node.name}", ""]

    # Docstring
    docstring = ast.get_docstring(class_node)
    if docstring:
        lines.extend([docstring.strip(), ""])

    # Fields
    fields = _extract_field_values(source, class_node)
    if fields:
        lines.append("## Fields")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for name, value in fields.items():
            val_str = repr(value)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            lines.append(f"| {name} | {val_str} |")
        lines.append("")

    # Methods
    methods = []
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args if a.arg != "self"]
            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")
            methods.append(f"- `{node.name}({', '.join(args)})`")
    if methods:
        lines.append("## Methods")
        lines.append("")
        lines.extend(methods)
        lines.append("")

    # Narrative fields
    for field_name in ("lessons_learned", "decision_log", "reflection", "notes"):
        if field_name in (fields or {}):
            val = fields[field_name]
            if isinstance(val, str) and len(val) > 40:
                lines.append(f"## {field_name.replace('_', ' ').title()}")
                lines.append("")
                lines.append(textwrap.dedent(val).strip())
                lines.append("")

    # Full source
    lines.append("## Source")
    lines.append("")
    lines.append("```python")
    lines.append(source.strip())
    lines.append("```")

    return "\n".join(lines) + "\n"


def compile_from_markdown(markdown: str) -> tuple[str, ValidationResult]:
    """Convert markdown back to Python source.

    If a ## Source code block exists, use it verbatim.
    Otherwise attempt best-effort reconstruction.
    """
    # Look for ## Source code block
    source_match = re.search(
        r"## Source\s*\n+```python\s*\n(.*?)```",
        markdown,
        re.DOTALL,
    )
    if source_match:
        source = source_match.group(1).strip() + "\n"
    else:
        # Best-effort: extract class name from heading
        heading_match = re.search(r"^# (.+)$", markdown, re.MULTILINE)
        class_name = heading_match.group(1).strip() if heading_match else "GeneratedModule"
        source = f"class {class_name}:\n    pass\n"

    result = validate(source)
    return source, result


# ---------------------------------------------------------------------------
# Validation policy (strict mode, suppression)
# ---------------------------------------------------------------------------

def _apply_policy(
    result: ValidationResult, strict: bool, suppress: list[str],
    error_codes: list[str] | None = None,
) -> ValidationResult:
    error_codes = error_codes or []
    if suppress:
        keep = lambda d: d.code not in suppress  # noqa: E731
        result.hard_errors = [d for d in result.hard_errors if keep(d)]
        result.auto_corrections = [d for d in result.auto_corrections if keep(d)]
        result.advice = [d for d in result.advice if keep(d)]
        if not result.hard_errors and not result.success and result.namespace is not None:
            result.success = True

    # --strict promotes WARNINGS (auto-corrections) only; advice/info stays
    # advisory. error_codes promotes specific codes regardless of tier.
    promoted = []
    if strict:
        promoted.extend(result.auto_corrections)
        result.auto_corrections = []
    if error_codes:
        for bucket_name in ("auto_corrections", "advice"):
            bucket = getattr(result, bucket_name)
            promoted.extend([d for d in bucket if d.code in error_codes])
            setattr(result, bucket_name, [d for d in bucket if d.code not in error_codes])

    if promoted:
        result.hard_errors.extend(promoted)
        result.success = False

    return result


def _extract_declared_type(
    class_node: ast.ClassDef,
    errors: list[Diagnostic],
    warnings: list[Diagnostic],
    expected_type: str | None,
) -> str | None:
    """Read an explicit __stato_type__ = "<type>" class attribute if present."""
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__stato_type__":
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    value = None
                valid = {t.value for t in ModuleType}
                if not isinstance(value, str) or value not in valid:
                    errors.append(Diagnostic(
                        code="E011",
                        message=f"Unknown __stato_type__ {value!r}. "
                                f"Allowed: {', '.join(sorted(valid))}",
                        severity=Severity.ERROR,
                        line=node.lineno,
                    ))
                    return None
                if expected_type and expected_type != value:
                    warnings.append(Diagnostic(
                        code="W008",
                        message=f"Declared __stato_type__ '{value}' overrides "
                                f"expected type '{expected_type}'",
                        severity=Severity.WARNING,
                        line=node.lineno,
                    ))
                return value
    return None


# ---------------------------------------------------------------------------
# Pass 1: Syntax
# ---------------------------------------------------------------------------

def _pass_syntax(
    source: str, errors: list[Diagnostic], advice: list[Diagnostic] | None = None
) -> ast.Module | None:
    from stato.core.astload import parse_collecting_warnings

    try:
        tree, warn_msgs = parse_collecting_warnings(source)
    except SyntaxError as e:
        errors.append(Diagnostic(
            code="E001",
            message=f"Syntax error: {e.msg}",
            severity=Severity.ERROR,
            line=e.lineno,
        ))
        return None

    # I009: authoring lint — invalid escape sequence in a non-raw string.
    if advice is not None:
        for msg in warn_msgs:
            if "escape sequence" in msg:
                advice.append(Diagnostic(
                    code="I009",
                    message=f"{msg} — use a raw string (r\"...\") to avoid the warning",
                    severity=Severity.INFO,
                ))
    return tree


# ---------------------------------------------------------------------------
# Pass 2: Structure
# ---------------------------------------------------------------------------

def _pass_structure(
    tree: ast.Module,
    errors: list[Diagnostic],
    warnings: list[Diagnostic],
) -> tuple[ast.ClassDef | None, str | None, bool]:
    """Find the primary class. Returns (class_node, class_name, has_docstring)."""
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]

    if not classes:
        errors.append(Diagnostic(
            code="E002",
            message="No class definition found",
            severity=Severity.ERROR,
        ))
        return None, None, False

    if len(classes) > 1:
        warnings.append(Diagnostic(
            code="W005",
            message=f"Multiple classes found, using first: {classes[0].name}",
            severity=Severity.WARNING,
            line=classes[0].lineno,
        ))

    class_node = classes[0]
    has_docstring = bool(ast.get_docstring(class_node))

    return class_node, class_node.name, has_docstring


# ---------------------------------------------------------------------------
# Pass 3: Type Inference
# ---------------------------------------------------------------------------

def _pass_type_infer(
    class_name: str,
    field_names: set[str],
    method_names: set[str],
    expected_type: str | None,
    warnings: list[Diagnostic],
    advice: list[Diagnostic],
    has_docstring: bool,
) -> ModuleType:
    inferred, confident = infer_module_type(class_name, field_names, method_names)

    if expected_type:
        try:
            module_type = ModuleType(expected_type)
        except ValueError:
            module_type = inferred
    else:
        module_type = inferred
        if not confident:
            warnings.append(Diagnostic(
                code="W006",
                message=f"Cannot confidently infer module type, defaulting to '{inferred.value}'",
                severity=Severity.WARNING,
            ))

    # I001: Naming convention check
    name_lower = class_name.lower()
    if module_type == ModuleType.MEMORY and not name_lower.endswith("state"):
        advice.append(Diagnostic(
            code="I001",
            message=f"Memory module class '{class_name}' should end with 'State'",
            severity=Severity.INFO,
        ))
    elif module_type == ModuleType.CONTEXT and not name_lower.endswith("context"):
        advice.append(Diagnostic(
            code="I001",
            message=f"Context module class '{class_name}' should end with 'Context'",
            severity=Severity.INFO,
        ))
    elif module_type == ModuleType.PROTOCOL and not name_lower.endswith("protocol"):
        advice.append(Diagnostic(
            code="I001",
            message=f"Protocol module class '{class_name}' should end with 'Protocol'",
            severity=Severity.INFO,
        ))

    # I002: No docstring
    if not has_docstring:
        advice.append(Diagnostic(
            code="I002",
            message="No docstring on class",
            severity=Severity.INFO,
        ))

    return module_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_members(class_node: ast.ClassDef) -> tuple[set[str], set[str]]:
    """Extract field names and method names from a class AST node."""
    field_names: set[str] = set()
    method_names: set[str] = set()

    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    field_names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                field_names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_names.add(node.name)

    return field_names, method_names


def _extract_field_values(source: str, class_node: ast.ClassDef) -> dict:
    """Extract literal field values from the class without executing it."""
    from stato.core.astload import extract_field_values

    return extract_field_values(source, class_node)


# ---------------------------------------------------------------------------
# Pass 4: Schema Check
# ---------------------------------------------------------------------------

def _pass_schema(
    module_type: ModuleType,
    field_names: set[str],
    method_names: set[str],
    errors: list[Diagnostic],
) -> None:
    schema = MODULE_SCHEMAS.get(module_type)
    if schema is None:
        return

    for req_field in schema["required_fields"]:
        if req_field not in field_names:
            errors.append(Diagnostic(
                code="E003",
                message=f"Missing required field: '{req_field}'",
                severity=Severity.ERROR,
            ))

    for req_method in schema["required_methods"]:
        if req_method not in method_names:
            errors.append(Diagnostic(
                code="E004",
                message=f"Missing required method: '{req_method}()'",
                severity=Severity.ERROR,
            ))


# ---------------------------------------------------------------------------
# Pass 5: Type Check + Auto-corrections
# ---------------------------------------------------------------------------

def _pass_type_check(
    source: str,
    class_node: ast.ClassDef,
    module_type: ModuleType,
    errors: list[Diagnostic],
    warnings: list[Diagnostic],
) -> str | None:
    """Check field types and apply auto-corrections. Returns corrected source or None."""
    schema = MODULE_SCHEMAS.get(module_type)
    if schema is None:
        return None

    field_types = schema.get("field_types", {})
    corrections: list[tuple[str, str, int]] = []  # (old, new, line)

    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            field_name = target.id
            if field_name not in field_types:
                continue

            expected = field_types[field_name]
            value_node = node.value

            # Try to evaluate the literal value
            try:
                actual_value = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                # Can't statically evaluate — skip type checking
                continue

            actual_type = type(actual_value)

            # Auto-correction: depends_on string → list
            if field_name == "depends_on" and actual_type is str:
                old_segment = ast.get_source_segment(source, value_node)
                if old_segment:
                    corrections.append((old_segment, f"[{old_segment}]", node.lineno))
                    warnings.append(Diagnostic(
                        code="W001",
                        message="depends_on is string, auto-wrapping in list",
                        severity=Severity.WARNING,
                        line=node.lineno,
                    ))
                continue

            # Auto-correction: depends_on int → list
            if field_name == "depends_on" and actual_type is int:
                old_segment = ast.get_source_segment(source, value_node)
                if old_segment:
                    corrections.append((old_segment, f"[{old_segment}]", node.lineno))
                    warnings.append(Diagnostic(
                        code="W002",
                        message="depends_on is int, auto-wrapping in list",
                        severity=Severity.WARNING,
                        line=node.lineno,
                    ))
                continue

            # Auto-correction: version missing patch
            if field_name == "version" and actual_type is str:
                if re.match(r"^\d+\.\d+$", actual_value):
                    old_segment = ast.get_source_segment(source, value_node)
                    if old_segment:
                        # Replace "1.0" with "1.0.0" inside the quotes
                        new_segment = old_segment.replace(
                            actual_value, actual_value + ".0"
                        )
                        corrections.append((old_segment, new_segment, node.lineno))
                        warnings.append(Diagnostic(
                            code="W003",
                            message=f"Version missing patch number, auto-fixing: "
                                    f"'{actual_value}' → '{actual_value}.0'",
                            severity=Severity.WARNING,
                            line=node.lineno,
                        ))
                continue

            # float fields accept ints (e.g. confidence = 1)
            if expected is float and isinstance(actual_value, (int, float)) \
                    and not isinstance(actual_value, bool):
                continue

            # Hard error: type mismatch that can't be auto-corrected
            if expected is not None and not isinstance(actual_value, expected):
                errors.append(Diagnostic(
                    code="E007",
                    message=f"Field '{field_name}' expects {expected.__name__}, "
                            f"got {actual_type.__name__}",
                    severity=Severity.ERROR,
                    line=node.lineno,
                ))

    if not corrections:
        return None

    # Apply corrections in reverse line order to avoid offset drift
    corrected = source
    corrections.sort(key=lambda c: c[2], reverse=True)
    for old, new, _line in corrections:
        corrected = corrected.replace(old, new, 1)

    return corrected


# ---------------------------------------------------------------------------
# Pass 6: Materialize (AST-only; replaces the former exec-based pass)
# ---------------------------------------------------------------------------

def _pass_materialize(
    source: str,
    class_name: str,
    module_type: ModuleType,
    errors: list[Diagnostic],
    advice: list[Diagnostic],
) -> dict | None:
    """Build the class from its AST — module code is never executed."""
    from stato.core.astload import materialize

    result = materialize(source)
    if result.namespace is None:
        errors.append(Diagnostic(
            code="E005",
            message=f"Could not materialize module: {result.error}",
            severity=Severity.ERROR,
        ))
        return None

    for skipped in result.skipped_fields:
        advice.append(Diagnostic(
            code="I007",
            message=f"Field '{skipped}' has a non-literal value — stored as-is "
                    "but not statically checkable (stato never executes module code)",
            severity=Severity.INFO,
        ))

    cls = result.namespace.get(class_name)
    if cls is None:
        return result.namespace

    # Check required methods are present and callable
    schema = MODULE_SCHEMAS.get(module_type)
    if schema:
        for method_name in schema.get("required_methods", []):
            method = getattr(cls, method_name, None)
            if method is None or not callable(method):
                errors.append(Diagnostic(
                    code="E006",
                    message=f"Required method '{method_name}()' is not callable",
                    severity=Severity.ERROR,
                ))

    return result.namespace


# ---------------------------------------------------------------------------
# Pass 7: Semantic (module-specific)
# ---------------------------------------------------------------------------

ALLOWED_PLAN_STATUSES = {"pending", "running", "complete", "failed", "blocked"}


def _pass_semantic(
    namespace: dict | None,
    class_name: str,
    module_type: ModuleType,
    errors: list[Diagnostic],
    warnings: list[Diagnostic],
    advice: list[Diagnostic],
) -> None:
    if namespace is None:
        return

    cls = namespace.get(class_name)
    if cls is None:
        return

    if module_type == ModuleType.PLAN:
        _validate_plan_semantics(cls, errors, warnings, advice)
    elif module_type == ModuleType.SKILL:
        _validate_skill_semantics(cls, advice)


def _validate_plan_semantics(
    cls: type,
    errors: list[Diagnostic],
    warnings: list[Diagnostic],
    advice: list[Diagnostic],
) -> None:
    steps = getattr(cls, "steps", None)
    if not isinstance(steps, list):
        return

    # Step ID uniqueness
    ids = [s.get("id") for s in steps if isinstance(s, dict)]
    seen_ids: set[int] = set()
    for step_id in ids:
        if step_id in seen_ids:
            errors.append(Diagnostic(
                code="E008",
                message=f"Duplicate step ID: {step_id}",
                severity=Severity.ERROR,
            ))
        seen_ids.add(step_id)

    # depends_on references valid IDs
    all_ids = set(ids)
    for step in steps:
        if not isinstance(step, dict):
            continue
        deps = step.get("depends_on", [])
        if not isinstance(deps, list):
            deps = [deps]
        for dep_id in deps:
            if dep_id not in all_ids:
                errors.append(Diagnostic(
                    code="E008",
                    message=f"Step {step.get('id')}: depends_on references "
                            f"nonexistent step {dep_id}",
                    severity=Severity.ERROR,
                ))

    # Status validation
    for step in steps:
        if not isinstance(step, dict):
            continue
        status = step.get("status")
        if status is None:
            # W004: auto-add pending
            step["status"] = "pending"
            warnings.append(Diagnostic(
                code="W004",
                message=f"Step {step.get('id')}: missing status, auto-set to 'pending'",
                severity=Severity.WARNING,
            ))
        elif status not in ALLOWED_PLAN_STATUSES:
            errors.append(Diagnostic(
                code="E010",
                message=f"Step {step.get('id')}: invalid status '{status}'. "
                        f"Allowed: {', '.join(sorted(ALLOWED_PLAN_STATUSES))}",
                severity=Severity.ERROR,
            ))

    # DAG acyclicity
    if not errors:
        cycles = _check_dag_acyclicity(steps)
        if cycles:
            errors.append(Diagnostic(
                code="E009",
                message=f"Circular dependency in plan step DAG: {cycles}",
                severity=Severity.ERROR,
            ))

    # skills_used on steps must be a list of strings
    for step in steps:
        if not isinstance(step, dict):
            continue
        skills_used = step.get("skills_used")
        if skills_used is None:
            continue
        if not isinstance(skills_used, list) or not all(
            isinstance(s, str) for s in skills_used
        ):
            errors.append(Diagnostic(
                code="E012",
                message=f"Step {step.get('id')}: skills_used must be a list of "
                        "skill names (strings)",
                severity=Severity.ERROR,
            ))

    # I004: no decision_log
    if not hasattr(cls, "decision_log") or not getattr(cls, "decision_log", None):
        advice.append(Diagnostic(
            code="I004",
            message="No decision_log on plan",
            severity=Severity.INFO,
        ))


def _validate_skill_semantics(cls: type, advice: list[Diagnostic]) -> None:
    # I003: No lessons_learned (structured `lessons` also counts)
    if not getattr(cls, "lessons_learned", None) and not getattr(cls, "lessons", None):
        advice.append(Diagnostic(
            code="I003",
            message="No lessons_learned on skill",
            severity=Severity.INFO,
        ))

    # I008: structured lessons entries should carry a recommendation
    lessons = getattr(cls, "lessons", None)
    if isinstance(lessons, list):
        for i, entry in enumerate(lessons):
            if not isinstance(entry, dict) or "recommendation" not in entry:
                advice.append(Diagnostic(
                    code="I008",
                    message=f"lessons[{i}] should be a dict with at least a "
                            "'recommendation' key (optional: condition, "
                            "confidence, review_by)",
                    severity=Severity.INFO,
                ))

    # confidence should be within 0..1
    confidence = getattr(cls, "confidence", None)
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        if not 0 <= confidence <= 1:
            advice.append(Diagnostic(
                code="I008",
                message=f"confidence should be between 0 and 1 (got {confidence})",
                severity=Severity.INFO,
            ))

    # I006: run() has no type hints
    run_method = getattr(cls, "run", None)
    if run_method and callable(run_method):
        hints = getattr(run_method, "__annotations__", {})
        if not hints:
            advice.append(Diagnostic(
                code="I006",
                message="run() has no type hints",
                severity=Severity.INFO,
            ))


def _check_dag_acyclicity(steps: list[dict]) -> list[list[int]]:
    """Check for cycles using DFS with coloring. Returns list of cycles found."""
    WHITE, GRAY, BLACK = 0, 1, 2

    # Build adjacency list
    adj: dict[int, list[int]] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        deps = step.get("depends_on", [])
        if not isinstance(deps, list):
            deps = [deps]
        # Edge: dependency → step (dep must complete before step)
        adj.setdefault(step_id, [])
        for dep in deps:
            adj.setdefault(dep, [])
            adj[dep].append(step_id)

    color = {node: WHITE for node in adj}
    cycles: list[list[int]] = []
    path: list[int] = []

    def dfs(node: int) -> bool:
        color[node] = GRAY
        path.append(node)
        for neighbor in adj.get(node, []):
            if color.get(neighbor) == GRAY:
                # Found cycle
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
                return True
            if color.get(neighbor) == WHITE:
                if dfs(neighbor):
                    return True
        path.pop()
        color[node] = BLACK
        return False

    for node in list(adj.keys()):
        if color[node] == WHITE:
            dfs(node)

    return cycles


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

def _build_result(
    errors: list[Diagnostic],
    warnings: list[Diagnostic],
    advice: list[Diagnostic],
    success: bool,
    module_type: ModuleType | None = None,
    class_name: str | None = None,
    corrected_source: str | None = None,
    namespace: dict | None = None,
) -> ValidationResult:
    return ValidationResult(
        success=success,
        module_type=module_type,
        class_name=class_name,
        hard_errors=errors,
        auto_corrections=warnings,
        advice=advice,
        corrected_source=corrected_source,
        namespace=namespace,
    )
