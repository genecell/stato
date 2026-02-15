"""Differ — field-by-field comparison of modules and snapshots."""
from __future__ import annotations

import ast
import zipfile
from dataclasses import dataclass
from pathlib import Path

import tomli


@dataclass
class FieldDiff:
    field: str
    value_a: str
    value_b: str
    changed: bool


def _extract_class_fields(source: str) -> dict:
    """Parse a module source and return field→value dict from the first class."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_node = node
            break
    if class_node is None:
        return {}

    # Execute to get runtime values
    namespace = {}
    try:
        exec(source, namespace)
    except Exception:
        return {}

    cls = namespace.get(class_node.name)
    if cls is None:
        return {}

    fields = {}
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    fields[target.id] = repr(getattr(cls, target.id, None))
    return fields


def diff_modules(source_a: str, source_b: str) -> list[FieldDiff]:
    """Compare two module sources field by field."""
    fields_a = _extract_class_fields(source_a)
    fields_b = _extract_class_fields(source_b)

    all_fields = sorted(set(fields_a) | set(fields_b))
    diffs = []
    for field in all_fields:
        val_a = fields_a.get(field, "<missing>")
        val_b = fields_b.get(field, "<missing>")
        diffs.append(FieldDiff(
            field=field,
            value_a=val_a,
            value_b=val_b,
            changed=val_a != val_b,
        ))
    return diffs


def diff_snapshots(archive_a: Path, archive_b: Path) -> dict:
    """Compare two snapshot archives.

    Returns dict with keys: added, removed, changed (lists of module paths).
    """
    def _read_modules(archive_path):
        modules = {}
        with zipfile.ZipFile(archive_path, "r") as zf:
            manifest = tomli.loads(zf.read("manifest.toml").decode("utf-8"))
            for member in manifest.get("included_modules", []):
                modules[member] = zf.read(member).decode("utf-8")
        return modules

    mods_a = _read_modules(archive_a)
    mods_b = _read_modules(archive_b)

    added = sorted(set(mods_b) - set(mods_a))
    removed = sorted(set(mods_a) - set(mods_b))
    changed = []

    for path in sorted(set(mods_a) & set(mods_b)):
        if mods_a[path] != mods_b[path]:
            changed.append(path)

    return {"added": added, "removed": removed, "changed": changed}


def diff_vs_backup(project_dir: Path, module_path: str) -> list[FieldDiff]:
    """Compare current module vs its most recent backup.

    Returns empty list if no backup exists.
    """
    stato_dir = project_dir / ".stato"
    current_file = stato_dir / module_path
    if not current_file.exists():
        return []

    history_dir = stato_dir / ".history"
    if not history_dir.exists():
        return []

    stem = Path(module_path).stem
    backups = sorted(history_dir.glob(f"{stem}.*.py"), key=lambda p: p.stat().st_mtime)
    if not backups:
        return []

    latest_backup = backups[-1]
    return diff_modules(latest_backup.read_text(), current_file.read_text())
