"""Shared pytest configuration and fixtures."""
import ast
import pytest
from pathlib import Path


@pytest.fixture
def project(tmp_path):
    """Create an initialized stato project."""
    from stato.core.state_manager import init_project
    return init_project(tmp_path)


def load_module(filepath: Path):
    """Helper: exec a module file and return the primary class."""
    source = filepath.read_text()
    namespace = {}
    exec(source, namespace)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return namespace[node.name]
    return None
