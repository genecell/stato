"""MemoryModule schema helpers and template reset."""
from __future__ import annotations

import ast
from stato.core.module import Diagnostic, Severity


def validate_memory(namespace: dict, class_name: str) -> list[Diagnostic]:
    """Memory-specific validation beyond schema checks."""
    return []


def reset_memory_for_template(source: str) -> str:
    """Template mode: phase -> 'init', clear error_history,
    rename reflection -> prior_reflection.
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

    nodes_to_remove = []

    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            if target.id == "phase":
                node.value = ast.Constant(value="init")
            elif target.id == "error_history":
                node.value = ast.List(elts=[], ctx=ast.Load())
            elif target.id == "reflection":
                target.id = "prior_reflection"

    return ast.unparse(tree)
