"""
Diff tests. Pure Python, no LLM.
"""
from stato.core.state_manager import init_project, write_module
from stato.core.composer import snapshot
from stato.core.differ import diff_modules, diff_snapshots, diff_vs_backup
from tests.fixtures import VALID_QC_SKILL


def test_diff_detects_version_change(tmp_path):
    """diff_vs_backup detects version field changed."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    updated = VALID_QC_SKILL.replace('version = "1.2.0"', 'version = "1.3.0"')
    write_module(project, "skills/qc.py", updated)
    diffs = diff_vs_backup(project, "skills/qc.py")
    assert any(d.field == "version" and d.changed for d in diffs)


def test_diff_detects_param_change(tmp_path):
    """diff_modules detects default_params change."""
    a = VALID_QC_SKILL
    b = VALID_QC_SKILL.replace('"max_pct_mito": 20', '"max_pct_mito": 25')
    diffs = diff_modules(a, b)
    assert any(d.field == "default_params" and d.changed for d in diffs)


def test_diff_snapshots(tmp_path):
    """diff_snapshots detects changed modules between archives."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    archive_a = snapshot(project, name="v1")

    updated = VALID_QC_SKILL.replace('version = "1.2.0"', 'version = "1.3.0"')
    write_module(project, "skills/qc.py", updated)
    archive_b = snapshot(project, name="v2")

    result = diff_snapshots(archive_a, archive_b)
    assert "skills/qc.py" in result["changed"]


def test_diff_no_backup_returns_empty(tmp_path):
    """First write has no backup, diff_vs_backup returns empty list."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    diffs = diff_vs_backup(project, "skills/qc.py")
    assert diffs == []
