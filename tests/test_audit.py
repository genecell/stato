"""Tests for stato audit (WS1)."""
from datetime import date

from click.testing import CliRunner

from stato.cli import main
from stato.core.audit import audit_module
from stato.core.state_manager import init_project, write_module

HIGH_QUALITY_SKILL = '''
class QualityControl:
    """QC filtering for scRNA-seq."""
    name = "qc_filtering"
    version = "1.2.0"
    source = "debugging session 2026-06-01"
    updated_at = "2026-06-14"
    confidence = 0.9
    default_params = {"min_genes": 200, "max_pct_mito": 20}
    lessons_learned = """
    - Cortex: max_pct_mito=20 keeps ~85% of cells
    """
    def run(self, adata, min_genes: int = 200) -> dict:
        return {}
'''

BARE_SKILL = '''
class Thing:
    name = "thing"
    def run(self):
        pass
'''


def test_high_quality_scores_high():
    report = audit_module(HIGH_QUALITY_SKILL, today=date(2026, 7, 1))
    assert report.module_type == "skill"
    assert report.score >= 9.0
    assert not report.failed


def test_bare_skill_scores_low_with_reasons():
    report = audit_module(BARE_SKILL, today=date(2026, 7, 1))
    assert report.score < 4.0
    failed = {c.key for c in report.failed}
    assert {"docstring", "provenance", "lessons", "version", "confidence"} <= failed


def test_stale_review_flagged():
    src = HIGH_QUALITY_SKILL.replace(
        'lessons_learned = """',
        'lessons = [{"recommendation": "x", "review_by": "2026-01-01"}]\n    lessons_learned = """',
    )
    report = audit_module(src, today=date(2026, 7, 1))
    assert any(c.key == "no_stale_lessons" and not c.passed for c in report.checks)


def test_future_review_not_flagged():
    src = HIGH_QUALITY_SKILL.replace(
        'lessons_learned = """',
        'lessons = [{"recommendation": "x", "review_by": "2027-01-01"}]\n    lessons_learned = """',
    )
    report = audit_module(src, today=date(2026, 7, 1))
    assert all(c.passed for c in report.checks if c.key == "no_stale_lessons")


def test_plan_without_decision_log_flagged():
    src = '''
class P:
    """A plan."""
    name = "p"
    objective = "do things"
    source = "x"
    steps = [{"id": 1, "action": "a", "status": "complete", "output": "done"}]
'''
    report = audit_module(src, today=date(2026, 7, 1))
    assert any(c.key == "decision_log" and not c.passed for c in report.checks)


def test_plan_completed_step_needs_output():
    src = '''
class P:
    """A plan."""
    name = "p"
    objective = "x"
    decision_log = "chose X because Y"
    source = "s"
    steps = [{"id": 1, "action": "a", "status": "complete"}]
'''
    report = audit_module(src, today=date(2026, 7, 1))
    assert any(c.key == "completed_have_output" and not c.passed for c in report.checks)


def test_score_is_zero_to_ten():
    for src in (HIGH_QUALITY_SKILL, BARE_SKILL):
        report = audit_module(src, today=date(2026, 7, 1))
        assert 0.0 <= report.score <= 10.0


def test_cli_json(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", HIGH_QUALITY_SKILL)
    write_module(tmp_path, "skills/bare.py", BARE_SKILL)
    result = CliRunner().invoke(main, ["audit", str(tmp_path / ".stato"), "--json"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert "aggregate" in payload
    assert len(payload["modules"]) >= 2


def test_cli_min_gate_fails(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/bare.py", BARE_SKILL)
    result = CliRunner().invoke(
        main, ["audit", str(tmp_path / ".stato"), "--min", "8"]
    )
    assert result.exit_code == 1


def test_cli_min_gate_passes(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", HIGH_QUALITY_SKILL)
    result = CliRunner().invoke(
        main, ["audit", str(tmp_path / ".stato" / "skills" / "qc.py"), "--min", "8"]
    )
    assert result.exit_code == 0


def test_directory_aggregate():
    import tempfile
    from pathlib import Path

    from stato.core.audit import audit_directory

    with tempfile.TemporaryDirectory() as d:
        init_project(Path(d))
        write_module(Path(d), "skills/qc.py", HIGH_QUALITY_SKILL)
        write_module(Path(d), "skills/bare.py", BARE_SKILL)
        reports, agg = audit_directory(Path(d) / ".stato")
        assert len(reports) == 2
        assert 0 <= agg <= 10
