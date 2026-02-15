"""Composer — the agent algebra: snapshot, import, inspect, slice, graft."""
from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

import tomli
import tomli_w

from stato import __version__

from stato.core.compiler import validate
from stato.core.module import ModuleType, ValidationResult, GraftResult


# ---------------------------------------------------------------------------
# Module discovery
# ---------------------------------------------------------------------------

def _discover_modules(as_dir: Path) -> list[dict]:
    """Walk .stato/ and find all valid .py module files.

    Returns list of dicts with keys:
        rel_path, full_path, module_type, class_name, namespace
    """
    modules = []
    for py_file in sorted(as_dir.rglob("*.py")):
        # Skip hidden dirs and __init__.py
        if ".history" in py_file.parts:
            continue
        if py_file.name.startswith("__"):
            continue

        rel = py_file.relative_to(as_dir)
        source = py_file.read_text()
        result = validate(source)
        if result.success and result.module_type:
            modules.append({
                "rel_path": PurePosixPath(rel),
                "full_path": py_file,
                "module_type": result.module_type,
                "class_name": result.class_name,
                "namespace": result.namespace,
            })
    return modules


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _filter_modules(
    all_modules: list[dict],
    modules: list[str] | None,
    types: list[str] | None,
    exclude: list[str] | None,
) -> list[dict]:
    selected = list(all_modules)

    if modules is not None:
        module_set = {m.replace(".py", "") for m in modules}
        selected = [
            m for m in selected
            if str(m["rel_path"]).replace(".py", "") in module_set
        ]

    if types is not None:
        type_set = {t.lower() for t in types}
        selected = [m for m in selected if m["module_type"].value in type_set]

    if exclude is not None:
        exclude_set = {e.lower() for e in exclude}
        selected = [
            m for m in selected
            if m["module_type"].value not in exclude_set
            and str(m["rel_path"]).replace(".py", "") not in exclude_set
        ]

    return selected


# ---------------------------------------------------------------------------
# Template reset
# ---------------------------------------------------------------------------

def _apply_template_reset(source: str, module_type: ModuleType) -> str:
    from stato.modules.skill import reset_skill_for_template
    from stato.modules.plan import reset_plan_for_template
    from stato.modules.memory import reset_memory_for_template
    from stato.modules.context import reset_context_for_template

    resetters = {
        ModuleType.SKILL: reset_skill_for_template,
        ModuleType.PLAN: reset_plan_for_template,
        ModuleType.MEMORY: reset_memory_for_template,
        ModuleType.CONTEXT: reset_context_for_template,
    }
    resetter = resetters.get(module_type)
    return resetter(source) if resetter else source


# ---------------------------------------------------------------------------
# Operation 1: SNAPSHOT
# ---------------------------------------------------------------------------

def snapshot(
    project_dir: Path,
    name: str,
    output_path: Path | None = None,
    description: str = "",
    template: bool = False,
    modules: list[str] | None = None,
    types: list[str] | None = None,
    exclude: list[str] | None = None,
    sanitize: bool = False,
) -> Path:
    """Bundle modules into a .stato zip archive with manifest.toml."""
    as_dir = project_dir / ".stato"
    if output_path is None:
        output_path = project_dir / f"{name}.stato"

    all_modules = _discover_modules(as_dir)
    selected = _filter_modules(all_modules, modules, types, exclude)

    is_partial = (modules is not None) or (types is not None) or (exclude is not None)

    scanner = None
    if sanitize:
        from stato.core.privacy import PrivacyScanner
        scanner = PrivacyScanner(
            ignore_file=project_dir / ".statoignore",
        )

    manifest = {
        "name": name,
        "description": description,
        "author": "",
        "created": datetime.now(timezone.utc).isoformat(),
        "stato_version": __version__,
        "partial": is_partial,
        "template": template,
        "included_modules": [str(m["rel_path"]) for m in selected],
    }

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.toml", tomli_w.dumps(manifest))
        for mod in selected:
            source = mod["full_path"].read_text()
            if template:
                source = _apply_template_reset(source, mod["module_type"])
            if scanner:
                source = scanner.sanitize(source)
            zf.writestr(str(mod["rel_path"]), source)

    return output_path


# ---------------------------------------------------------------------------
# Operation 2: IMPORT
# ---------------------------------------------------------------------------

def import_snapshot(
    project_dir: Path,
    archive_path: Path,
    modules: list[str] | None = None,
    types: list[str] | None = None,
    rename_as: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Extract modules from .stato archive into project's .stato/.

    Returns list of imported module relative paths.
    """
    as_dir = project_dir / ".stato"
    as_dir.mkdir(parents=True, exist_ok=True)
    (as_dir / "skills").mkdir(exist_ok=True)

    imported = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        manifest = tomli.loads(zf.read("manifest.toml").decode("utf-8"))
        included = manifest.get("included_modules", [])

        for member in included:
            if member == "manifest.toml":
                continue

            # Filter by specific modules
            if modules is not None:
                member_stem = member.replace(".py", "")
                if member_stem not in [m.replace(".py", "") for m in modules]:
                    continue

            # Filter by type
            if types is not None:
                source = zf.read(member).decode("utf-8")
                result = validate(source)
                if not result.success or result.module_type is None:
                    continue
                if result.module_type.value not in [t.lower() for t in types]:
                    continue

            if dry_run:
                imported.append(member)
                continue

            # Extract
            source = zf.read(member).decode("utf-8")
            target = as_dir / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
            imported.append(member)

    return imported


# ---------------------------------------------------------------------------
# INSPECT
# ---------------------------------------------------------------------------

def inspect_archive(archive_path: Path) -> dict:
    """Preview archive contents without importing."""
    with zipfile.ZipFile(archive_path, "r") as zf:
        manifest = tomli.loads(zf.read("manifest.toml").decode("utf-8"))

        module_info = []
        for member in manifest.get("included_modules", []):
            source = zf.read(member).decode("utf-8")
            result = validate(source)
            module_info.append({
                "path": member,
                "type": result.module_type.value if result.module_type else "unknown",
                "class_name": result.class_name or "unknown",
                "valid": result.success,
            })

    return {
        "name": manifest.get("name", ""),
        "description": manifest.get("description", ""),
        "created": manifest.get("created", ""),
        "template": manifest.get("template", False),
        "partial": manifest.get("partial", False),
        "modules": manifest.get("included_modules", []),
        "module_details": module_info,
    }


# ---------------------------------------------------------------------------
# Operation 3: SLICE
# ---------------------------------------------------------------------------

def slice_modules(
    project_dir: Path,
    modules: list[str],
    output_path: Path | None = None,
    with_deps: bool = False,
    name: str = "",
) -> tuple[Path, list[str]]:
    """Extract specific modules with dependency awareness.

    Returns (archive_path, warnings).
    """
    as_dir = project_dir / ".stato"
    all_modules = _discover_modules(as_dir)
    warnings: list[str] = []

    # Resolve requested modules
    module_stems = {m.replace(".py", "") for m in modules}
    selected = [
        m for m in all_modules
        if str(m["rel_path"]).replace(".py", "") in module_stems
    ]

    if with_deps:
        selected, dep_warnings = _resolve_dependencies(selected, all_modules)
        warnings.extend(dep_warnings)
    else:
        # Warn about missing dependencies
        for mod in selected:
            deps = _get_depends_on(mod)
            for dep_name in deps:
                dep_in_project = any(
                    _module_provides(m, dep_name) for m in all_modules
                )
                dep_in_selected = any(
                    _module_provides(m, dep_name) for m in selected
                )
                if dep_in_project and not dep_in_selected:
                    warnings.append(
                        f"Module '{mod['rel_path']}' depends on '{dep_name}' "
                        f"which exists in project but won't be included in slice."
                    )

    if not name:
        name = "slice-" + "-".join(m.replace("/", "_") for m in modules)
    if output_path is None:
        output_path = project_dir / f"{name}.stato"

    manifest = {
        "name": name,
        "description": f"Sliced modules: {', '.join(modules)}",
        "author": "",
        "created": datetime.now(timezone.utc).isoformat(),
        "stato_version": __version__,
        "partial": True,
        "template": False,
        "included_modules": [str(m["rel_path"]) for m in selected],
    }

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.toml", tomli_w.dumps(manifest))
        for mod in selected:
            source = mod["full_path"].read_text()
            zf.writestr(str(mod["rel_path"]), source)

    return output_path, warnings


# ---------------------------------------------------------------------------
# Operation 4: GRAFT
# ---------------------------------------------------------------------------

def graft(
    project_dir: Path,
    source_path: Path,
    module: str | None = None,
    rename_as: str | None = None,
    on_conflict: str = "ask",
) -> GraftResult:
    """Add module from external source (.stato archive or single .py file)."""
    as_dir = project_dir / ".stato"
    result = GraftResult(success=False)

    if zipfile.is_zipfile(source_path):
        with zipfile.ZipFile(source_path, "r") as zf:
            manifest = tomli.loads(zf.read("manifest.toml").decode("utf-8"))
            members = manifest.get("included_modules", [])

            if module:
                module_stem = module.replace(".py", "")
                members = [
                    m for m in members
                    if m.replace(".py", "") == module_stem
                ]

            for member in members:
                source_code = zf.read(member).decode("utf-8")
                _graft_single(
                    as_dir, member, source_code,
                    rename_as, on_conflict, result,
                )
    else:
        # Single .py file
        source_code = source_path.read_text()
        rel_path = source_path.name
        if "/" not in rel_path and not rel_path.startswith("skills"):
            rel_path = f"skills/{rel_path}"
        _graft_single(
            as_dir, rel_path, source_code,
            rename_as, on_conflict, result,
        )

    if not result.has_conflict or on_conflict in ("replace", "rename", "skip"):
        result.success = True

    return result


def _graft_single(
    as_dir: Path,
    rel_path: str,
    source: str,
    rename_as: str | None,
    on_conflict: str,
    result: GraftResult,
) -> None:
    """Graft a single module file into the project."""
    vr = validate(source)
    if not vr.success:
        result.validation = vr
        result.has_conflict = True
        result.conflicts.append(f"Validation failed for {rel_path}")
        return

    # Determine target path
    if rename_as:
        parent = str(PurePosixPath(rel_path).parent)
        target_rel = f"{parent}/{rename_as}.py" if parent != "." else f"{rename_as}.py"
    else:
        target_rel = rel_path

    target = as_dir / target_rel

    # Check for conflicts
    if target.exists():
        result.has_conflict = True
        result.conflicts.append(f"Name collision: '{target_rel}' already exists")

        if on_conflict == "skip":
            return
        elif on_conflict == "replace":
            pass
        elif on_conflict == "rename":
            stem = PurePosixPath(target_rel).stem
            parent = str(PurePosixPath(target_rel).parent)
            target_rel = (
                f"{parent}/{stem}_imported.py"
                if parent != "."
                else f"{stem}_imported.py"
            )
            target = as_dir / target_rel
        elif on_conflict == "ask":
            return

    # Write
    target.parent.mkdir(parents=True, exist_ok=True)
    write_source = vr.corrected_source or source
    target.write_text(write_source)
    result.imported_modules.append(target_rel)
    result.validation = vr

    # Check for dependency warnings
    if vr.namespace and vr.class_name:
        cls = vr.namespace.get(vr.class_name)
        deps = getattr(cls, "depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        if isinstance(deps, list):
            for dep in deps:
                dep_skill = as_dir / "skills" / f"{dep}.py"
                dep_root = as_dir / f"{dep}.py"
                if not dep_skill.exists() and not dep_root.exists():
                    result.dependency_warnings.append(
                        f"Module '{target_rel}' depends on '{dep}' "
                        f"which is not in the project"
                    )


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_depends_on(mod: dict) -> list[str]:
    """Extract depends_on from a validated module's namespace."""
    if not mod.get("namespace") or not mod.get("class_name"):
        return []
    cls = mod["namespace"].get(mod["class_name"])
    if cls is None:
        return []
    deps = getattr(cls, "depends_on", [])
    if isinstance(deps, str):
        return [deps]
    if isinstance(deps, list):
        return [str(d) for d in deps]
    return []


def _module_provides(mod: dict, dep_name: str) -> bool:
    """Check if a module provides/satisfies a dependency name."""
    if not mod.get("namespace") or not mod.get("class_name"):
        return False
    cls = mod["namespace"].get(mod["class_name"])
    if cls is None:
        return False
    name = getattr(cls, "name", "")
    return name == dep_name


def _resolve_dependencies(
    selected: list[dict],
    all_modules: list[dict],
) -> tuple[list[dict], list[str]]:
    """Add dependency modules to selected list."""
    warnings: list[str] = []
    selected_keys = {str(m["rel_path"]) for m in selected}
    to_check = list(selected)

    while to_check:
        mod = to_check.pop(0)
        for dep_name in _get_depends_on(mod):
            for candidate in all_modules:
                if _module_provides(candidate, dep_name):
                    key = str(candidate["rel_path"])
                    if key not in selected_keys:
                        selected.append(candidate)
                        selected_keys.add(key)
                        to_check.append(candidate)
                        warnings.append(
                            f"Auto-included dependency: '{candidate['rel_path']}' "
                            f"(needed by '{mod['rel_path']}')"
                        )
    return selected, warnings
