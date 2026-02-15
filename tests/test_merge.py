"""Tests for stato merge — archive merging with conflict resolution."""
import zipfile
from pathlib import Path

import pytest
import tomli_w

from stato.core.merger import (
    MergeStrategy,
    merge_archives,
    extract_archive,
    create_archive,
    discover_modules,
    extract_module_fields,
)
from tests.fixtures import VALID_QC_SKILL, VALID_NORMALIZE_SKILL, VALID_MEMORY, VALID_CONTEXT


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def create_test_archive(tmp_path: Path, name: str,
                        modules: dict[str, str]) -> Path:
    """Create a .stato archive from a dict of {rel_path: source}."""
    archive_path = tmp_path / f"{name}.stato"
    manifest = {
        "name": name,
        "description": f"Test archive: {name}",
        "author": "",
        "created": "2026-01-01T00:00:00+00:00",
        "stato_version": "0.5.0",
        "partial": False,
        "template": False,
        "included_modules": list(modules.keys()),
    }
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.toml", tomli_w.dumps(manifest))
        for rel_path, source in modules.items():
            zf.writestr(rel_path, source)
    return archive_path


# ---------------------------------------------------------------------------
# Merge-specific fixtures
# ---------------------------------------------------------------------------

QC_MITO_20 = '''
class QualityControl:
    name = "qc_filtering"
    version = "1.2.0"
    depends_on = ["scanpy"]
    default_params = {
        "min_genes": 200,
        "max_genes": 5000,
        "max_pct_mito": 20,
    }
    lessons_learned = """
    - Cortex tissue: max_pct_mito=20 retains ~85% of cells
    """
    @staticmethod
    def run(**kwargs): pass
'''

QC_MITO_40 = '''
class QualityControl:
    name = "qc_filtering"
    version = "1.3.0"
    depends_on = ["scanpy", "anndata"]
    default_params = {
        "min_genes": 200,
        "max_genes": 5000,
        "max_pct_mito": 40,
    }
    lessons_learned = """
    - FFPE samples: increase to max_pct_mito=40
    """
    @staticmethod
    def run(**kwargs): pass
'''


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_merge_disjoint_skills(tmp_path):
    """Two archives with different modules -> union contains both."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": VALID_QC_SKILL,
    })
    right = create_test_archive(tmp_path, "right", {
        "skills/normalize.py": VALID_NORMALIZE_SKILL,
    })

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir)
    assert "skills/qc.py" in result.modules
    assert "skills/normalize.py" in result.modules
    assert len(result.conflicts) == 0
    assert "skills/qc.py" in result.left_only
    assert "skills/normalize.py" in result.right_only


def test_merge_overlapping_skills_union(tmp_path):
    """Two archives with same module -> merged with union strategy."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": QC_MITO_20,
    })
    right = create_test_archive(tmp_path, "right", {
        "skills/qc.py": QC_MITO_40,
    })

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir, MergeStrategy.UNION)
    assert "skills/qc.py" in result.modules
    assert "skills/qc.py" in result.merged

    # Merged source should exist
    merged_source = result.modules["skills/qc.py"]
    assert "qc_filtering" in merged_source


def test_merge_param_conflict(tmp_path):
    """Conflicting param values should be reported."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": QC_MITO_20,
    })
    right = create_test_archive(tmp_path, "right", {
        "skills/qc.py": QC_MITO_40,
    })

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir, MergeStrategy.UNION)
    param_conflicts = [c for c in result.conflicts
                       if "max_pct_mito" in c.field]
    assert len(param_conflicts) == 1
    assert "20" in param_conflicts[0].left_value
    assert "40" in param_conflicts[0].right_value


def test_merge_prefer_left(tmp_path):
    """Prefer-left strategy keeps left value on conflict."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": QC_MITO_20,
    })
    right = create_test_archive(tmp_path, "right", {
        "skills/qc.py": QC_MITO_40,
    })

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir, MergeStrategy.PREFER_LEFT)
    conflicts = [c for c in result.conflicts if "max_pct_mito" in c.field]
    assert len(conflicts) == 1
    assert "left" in conflicts[0].resolution


def test_merge_prefer_right(tmp_path):
    """Prefer-right strategy keeps right value on conflict."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": QC_MITO_20,
    })
    right = create_test_archive(tmp_path, "right", {
        "skills/qc.py": QC_MITO_40,
    })

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir, MergeStrategy.PREFER_RIGHT)
    conflicts = [c for c in result.conflicts if "max_pct_mito" in c.field]
    assert len(conflicts) == 1
    assert "right" in conflicts[0].resolution


def test_merge_deps_union(tmp_path):
    """Dependencies from both sides are unioned."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": QC_MITO_20,
    })
    right = create_test_archive(tmp_path, "right", {
        "skills/qc.py": QC_MITO_40,
    })

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir, MergeStrategy.UNION)
    merged_source = result.modules["skills/qc.py"]
    # Both "scanpy" and "anndata" should be in merged deps
    assert "scanpy" in merged_source
    assert "anndata" in merged_source


def test_merge_lessons_deduplicated(tmp_path):
    """Duplicate lesson lines should be deduplicated."""
    skill_a = '''
class SkillA:
    name = "skill_a"
    version = "1.0.0"
    depends_on = []
    default_params = {}
    lessons_learned = """
    - Lesson one
    - Lesson two
    """
    @staticmethod
    def run(**kwargs): pass
'''
    skill_b = '''
class SkillB:
    name = "skill_a"
    version = "1.0.0"
    depends_on = []
    default_params = {}
    lessons_learned = """
    - Lesson two
    - Lesson three
    """
    @staticmethod
    def run(**kwargs): pass
'''
    left = create_test_archive(tmp_path, "left", {"skills/a.py": skill_a})
    right = create_test_archive(tmp_path, "right", {"skills/a.py": skill_b})

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    extract_archive(right, right_dir)

    result = merge_archives(left_dir, right_dir, MergeStrategy.UNION)
    merged_source = result.modules["skills/a.py"]

    # Count occurrences of "Lesson two" — should appear only once
    assert merged_source.count("Lesson two") == 1
    assert "Lesson one" in merged_source
    assert "Lesson three" in merged_source


def test_merge_empty_archive(tmp_path):
    """Merging with an empty archive returns the other side's modules."""
    left = create_test_archive(tmp_path, "left", {
        "skills/qc.py": VALID_QC_SKILL,
    })
    right = create_test_archive(tmp_path, "right", {})

    left_dir = tmp_path / "left_dir"
    right_dir = tmp_path / "right_dir"
    extract_archive(left, left_dir)
    # right_dir needs to exist even if empty
    right_dir.mkdir(parents=True, exist_ok=True)

    result = merge_archives(left_dir, right_dir)
    assert "skills/qc.py" in result.modules
    assert len(result.right_only) == 0
    assert "skills/qc.py" in result.left_only
