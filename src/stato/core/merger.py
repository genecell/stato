"""Merger — combine two stato archives with conflict resolution."""
from __future__ import annotations

import ast
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from stato import __version__

import tomli
import tomli_w

from stato.core.module import ModuleType, infer_module_type


class MergeStrategy(Enum):
    UNION = "union"
    PREFER_LEFT = "prefer-left"
    PREFER_RIGHT = "prefer-right"


@dataclass
class MergeConflict:
    """A conflict between two modules."""
    module_path: str
    field: str
    left_value: str
    right_value: str
    resolution: str


@dataclass
class MergeResult:
    """Result of merging two archives."""
    modules: dict[str, str] = field(default_factory=dict)
    conflicts: list[MergeConflict] = field(default_factory=list)
    left_only: list[str] = field(default_factory=list)
    right_only: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Archive helpers
# ---------------------------------------------------------------------------

def extract_archive(archive_path: Path, target_dir: Path) -> None:
    """Extract a .stato archive to a directory (modules only, no manifest)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        manifest = tomli.loads(zf.read("manifest.toml").decode("utf-8"))
        for member in manifest.get("included_modules", []):
            source = zf.read(member).decode("utf-8")
            target = target_dir / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)


def create_archive(source_dir: Path, output_path: Path,
                   name: str = "merged") -> Path:
    """Pack a directory of modules into a .stato archive."""
    modules_list = []
    for py_file in sorted(source_dir.rglob("*.py")):
        if py_file.name.startswith("__"):
            continue
        rel = str(py_file.relative_to(source_dir))
        modules_list.append(rel)

    manifest = {
        "name": name,
        "description": f"Merged archive",
        "author": "",
        "created": datetime.now(timezone.utc).isoformat(),
        "stato_version": __version__,
        "partial": False,
        "template": False,
        "included_modules": modules_list,
    }

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.toml", tomli_w.dumps(manifest))
        for rel in modules_list:
            source = (source_dir / rel).read_text()
            zf.writestr(rel, source)

    return output_path


# ---------------------------------------------------------------------------
# Module discovery
# ---------------------------------------------------------------------------

def discover_modules(stato_dir: Path) -> dict[str, str]:
    """Find all .py modules in a stato directory."""
    modules: dict[str, str] = {}
    for py_file in sorted(stato_dir.rglob("*.py")):
        if py_file.name.startswith("__"):
            continue
        rel_path = str(py_file.relative_to(stato_dir))
        modules[rel_path] = py_file.read_text()
    return modules


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def extract_module_fields(source: str) -> dict | None:
    """Execute source and extract class fields + inferred type."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_node = node
            break

    if class_node is None:
        return None

    namespace: dict = {}
    try:
        exec(source, namespace)
    except Exception:
        return None

    cls = namespace.get(class_node.name)
    if cls is None:
        return None

    # Extract fields
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

    module_type, _ = infer_module_type(class_node.name, field_names, method_names)

    fields: dict = {"_type": module_type.value, "class_name": class_node.name}
    for name in field_names:
        val = getattr(cls, name, None)
        if val is not None:
            fields[name] = val

    return fields


# ---------------------------------------------------------------------------
# Main merge
# ---------------------------------------------------------------------------

def merge_archives(left_dir: Path, right_dir: Path,
                   strategy: MergeStrategy = MergeStrategy.UNION) -> MergeResult:
    """Merge two expanded stato archive directories."""
    left_modules = discover_modules(left_dir)
    right_modules = discover_modules(right_dir)

    left_paths = set(left_modules.keys())
    right_paths = set(right_modules.keys())

    result = MergeResult(
        left_only=sorted(left_paths - right_paths),
        right_only=sorted(right_paths - left_paths),
    )

    for path in result.left_only:
        result.modules[path] = left_modules[path]

    for path in result.right_only:
        result.modules[path] = right_modules[path]

    common = sorted(left_paths & right_paths)
    for path in common:
        merged_source, conflicts = merge_module(
            left_modules[path], right_modules[path], path, strategy
        )
        result.modules[path] = merged_source
        result.conflicts.extend(conflicts)
        result.merged.append(path)

    return result


def merge_module(left_source: str, right_source: str,
                 path: str, strategy: MergeStrategy) -> tuple[str, list[MergeConflict]]:
    """Merge two versions of the same module."""
    left_fields = extract_module_fields(left_source)
    right_fields = extract_module_fields(right_source)

    if not left_fields or not right_fields:
        if strategy == MergeStrategy.PREFER_RIGHT:
            return right_source, []
        return left_source, []

    module_type = left_fields.get("_type", "unknown")

    if module_type == "skill":
        return merge_skill(left_fields, right_fields, path, strategy)
    elif module_type == "plan":
        return merge_plan(left_source, left_fields, right_fields, path, strategy)
    elif module_type == "memory":
        return merge_memory(left_fields, right_fields, path, strategy)
    elif module_type == "context":
        return merge_context(left_fields, right_fields, path, strategy)
    else:
        if strategy == MergeStrategy.PREFER_RIGHT:
            return right_source, []
        return left_source, []


# ---------------------------------------------------------------------------
# Type-specific mergers
# ---------------------------------------------------------------------------

def merge_skill(left: dict, right: dict, path: str,
                strategy: MergeStrategy) -> tuple[str, list[MergeConflict]]:
    """Merge two skill modules."""
    from stato.core.converter import generate_skill_source

    conflicts: list[MergeConflict] = []

    # Version: take higher
    left_ver = left.get("version", "1.0.0")
    right_ver = right.get("version", "1.0.0")
    merged_version = max(str(left_ver), str(right_ver))

    # depends_on: union
    left_deps = set(_as_list(left.get("depends_on", [])))
    right_deps = set(_as_list(right.get("depends_on", [])))
    merged_deps = sorted(left_deps | right_deps)

    # default_params: union with conflict detection
    left_params = left.get("default_params", {}) or {}
    right_params = right.get("default_params", {}) or {}
    merged_params: dict = {}

    all_keys = set(list(left_params.keys()) + list(right_params.keys()))
    for key in sorted(all_keys):
        if key in left_params and key in right_params:
            if left_params[key] != right_params[key]:
                winner = "left" if strategy != MergeStrategy.PREFER_RIGHT else "right"
                conflicts.append(MergeConflict(
                    module_path=path,
                    field=f"default_params.{key}",
                    left_value=str(left_params[key]),
                    right_value=str(right_params[key]),
                    resolution=f"{winner} value kept",
                ))
                merged_params[key] = (
                    right_params[key] if strategy == MergeStrategy.PREFER_RIGHT
                    else left_params[key]
                )
            else:
                merged_params[key] = left_params[key]
        elif key in left_params:
            merged_params[key] = left_params[key]
        else:
            merged_params[key] = right_params[key]

    # lessons_learned: concatenate + deduplicate
    left_lessons = str(left.get("lessons_learned", "") or "").strip()
    right_lessons = str(right.get("lessons_learned", "") or "").strip()

    if left_lessons and right_lessons:
        merged_lessons = left_lessons + "\n" + right_lessons
    else:
        merged_lessons = left_lessons or right_lessons

    seen: set[str] = set()
    unique: list[str] = []
    for line in merged_lessons.split("\n"):
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            unique.append(line)
    merged_lessons = "\n".join(unique)

    name = left.get("name", right.get("name", "unnamed"))
    description = left.get("description", right.get("description", ""))

    merged_source = generate_skill_source(
        name=str(name),
        description=str(description),
        depends_on=merged_deps,
        default_params=merged_params,
        lessons_learned=merged_lessons,
    )

    # Patch version to merged_version
    merged_source = merged_source.replace('version = "1.0.0"',
                                          f'version = "{merged_version}"', 1)

    return merged_source, conflicts


def merge_plan(left_source: str, left: dict, right: dict, path: str,
               strategy: MergeStrategy) -> tuple[str, list[MergeConflict]]:
    """Merge two plan modules. Take the one with more progress."""
    left_steps = left.get("steps", []) or []
    right_steps = right.get("steps", []) or []

    left_done = sum(1 for s in left_steps
                    if isinstance(s, dict) and s.get("status") == "complete")
    right_done = sum(1 for s in right_steps
                     if isinstance(s, dict) and s.get("status") == "complete")

    if strategy == MergeStrategy.PREFER_RIGHT:
        winner_source = _rebuild_from_fields(right, "plan")
    elif strategy == MergeStrategy.PREFER_LEFT:
        winner_source = _rebuild_from_fields(left, "plan")
    else:
        # Union: take the one with more progress
        if right_done > left_done:
            winner_source = _rebuild_from_fields(right, "plan")
        else:
            winner_source = _rebuild_from_fields(left, "plan")

    # Concatenate decision logs
    left_log = str(left.get("decision_log", "") or "").strip()
    right_log = str(right.get("decision_log", "") or "").strip()
    if left_log and right_log and left_log != right_log:
        combined = left_log + "\n" + right_log
        winner_source = winner_source.replace(
            f'decision_log = """\n{left_log}',
            f'decision_log = """\n{combined}',
        )

    return winner_source, []


def merge_memory(left: dict, right: dict, path: str,
                 strategy: MergeStrategy) -> tuple[str, list[MergeConflict]]:
    """Merge two memory modules."""
    if strategy == MergeStrategy.PREFER_RIGHT:
        base, other = right, left
    elif strategy == MergeStrategy.PREFER_LEFT:
        base, other = left, right
    else:
        base, other = left, right

    # Union known_issues
    issues = dict(base.get("known_issues", {}) or {})
    issues.update(other.get("known_issues", {}) or {})

    # Concatenate reflection
    left_refl = str(left.get("reflection", "") or "").strip()
    right_refl = str(right.get("reflection", "") or "").strip()
    if left_refl and right_refl and left_refl != right_refl:
        reflection = left_refl + "\n" + right_refl
    else:
        reflection = left_refl or right_refl

    phase = base.get("phase", other.get("phase", "unknown"))
    tasks = list(base.get("tasks", []) or [])
    other_tasks = list(other.get("tasks", []) or [])
    for t in other_tasks:
        if t not in tasks:
            tasks.append(t)

    source = _generate_memory_source(
        phase=str(phase),
        tasks=tasks,
        known_issues=issues,
        reflection=reflection,
    )

    return source, []


def merge_context(left: dict, right: dict, path: str,
                  strategy: MergeStrategy) -> tuple[str, list[MergeConflict]]:
    """Merge two context modules."""
    from stato.core.converter import generate_context_source

    if strategy == MergeStrategy.PREFER_RIGHT:
        base, other = right, left
    else:
        base, other = left, right

    project = str(base.get("project", other.get("project", "merged")))
    description = str(base.get("description", other.get("description", "")))

    # Union environment
    env = dict(other.get("environment", {}) or {})
    env.update(base.get("environment", {}) or {})

    # Union conventions (deduplicate)
    convs = list(base.get("conventions", []) or [])
    other_convs = list(other.get("conventions", []) or [])
    for c in other_convs:
        if c not in convs:
            convs.append(c)

    source = generate_context_source(
        project=project,
        description=description,
        environment=env,
        conventions=convs,
    )

    return source, []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_list(val) -> list:
    """Ensure value is a list."""
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []


def _rebuild_from_fields(fields: dict, module_type: str) -> str:
    """Rebuild module source from extracted fields."""
    if module_type == "plan":
        return _generate_plan_source(fields)
    elif module_type == "memory":
        return _generate_memory_source(
            phase=str(fields.get("phase", "unknown")),
            tasks=list(fields.get("tasks", []) or []),
            known_issues=dict(fields.get("known_issues", {}) or {}),
            reflection=str(fields.get("reflection", "") or ""),
        )
    return ""


def _generate_plan_source(fields: dict) -> str:
    """Generate a plan module source string."""
    class_name = fields.get("class_name", "MergedPlan")
    name = fields.get("name", "merged_plan")
    objective = fields.get("objective", "")
    steps = fields.get("steps", [])
    decision_log = str(fields.get("decision_log", "") or "").strip()

    steps_str = repr(steps)
    log_section = (f'    decision_log = """\n{decision_log}\n    """'
                   if decision_log else '')

    return f'''class {class_name}:
    name = "{name}"
    objective = "{objective}"
    steps = {steps_str}
{log_section}
'''


def _generate_memory_source(phase: str, tasks: list, known_issues: dict,
                            reflection: str) -> str:
    """Generate a memory module source string."""
    refl_escaped = reflection.replace('"""', '\\"\\"\\"')

    return f'''class MergedState:
    phase = "{phase}"
    tasks = {repr(tasks)}
    known_issues = {repr(known_issues)}
    reflection = """
{refl_escaped}
    """
'''
