"""Bundle parser — extract stato modules from a single Python file."""
from __future__ import annotations

import ast
from pathlib import Path
from dataclasses import dataclass


@dataclass
class BundleParseResult:
    """Result of parsing a bundle file."""
    skills: dict[str, str]      # name → module source
    plan: str | None
    memory: str | None
    context: str | None
    errors: list[str]


def parse_bundle(bundle_path: Path) -> BundleParseResult:
    """Parse a stato bundle file into individual module sources.

    Strategy: Use ast.parse to safely extract the module variables.
    This avoids exec() on untrusted files.
    """
    content = bundle_path.read_text()
    errors: list[str] = []
    skills: dict[str, str] = {}
    plan = None
    memory = None
    context = None

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return BundleParseResult({}, None, None, None, [f"Bundle syntax error: {e}"])

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id

                    if name == "SKILLS" and isinstance(node.value, ast.Dict):
                        # Extract each skill from the dict
                        for key, value in zip(node.value.keys, node.value.values):
                            if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
                                skill_name = key.value
                                skill_source = value.value
                                if isinstance(skill_name, str) and isinstance(skill_source, str):
                                    skills[skill_name] = skill_source.strip()

                    elif name == "PLAN" and isinstance(node.value, ast.Constant):
                        plan = node.value.value.strip() if isinstance(node.value.value, str) else None

                    elif name == "MEMORY" and isinstance(node.value, ast.Constant):
                        memory = node.value.value.strip() if isinstance(node.value.value, str) else None

                    elif name == "CONTEXT" and isinstance(node.value, ast.Constant):
                        context = node.value.value.strip() if isinstance(node.value.value, str) else None

    return BundleParseResult(skills, plan, memory, context, errors)
