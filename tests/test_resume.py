"""Resume command tests. Pure Python, no LLM."""
from stato.core.resume import generate_resume
from stato.core.state_manager import init_project, write_module
from tests.fixtures import (
    VALID_CONTEXT,
    VALID_PLAN,
    VALID_QC_SKILL,
    VALID_MEMORY,
)


def test_resume_includes_project_name(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "context.py", VALID_CONTEXT)
    result = generate_resume(project / ".stato")
    assert "cortex_scrna" in result


def test_resume_includes_plan_progress(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "plan.py", VALID_PLAN)
    result = generate_resume(project / ".stato")
    assert "3/7" in result or "complete" in result


def test_resume_includes_skill_params(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    result = generate_resume(project / ".stato")
    assert "qc_filtering" in result
    assert "max_pct_mito" in result


def test_resume_includes_known_issues(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "memory.py", VALID_MEMORY)
    result = generate_resume(project / ".stato")
    assert "batch_effect" in result or "known_issues" in result.lower()


def test_resume_brief_is_one_paragraph(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "context.py", VALID_CONTEXT)
    write_module(project, "plan.py", VALID_PLAN)
    result = generate_resume(project / ".stato", brief=True)
    # Should be a single paragraph (no double newlines)
    assert "\n\n" not in result


def test_resume_empty_project(tmp_path):
    project = init_project(tmp_path)
    result = generate_resume(project / ".stato")
    # Should not crash on empty project
    assert isinstance(result, str)


def test_resume_raw_output(tmp_path):
    """Raw output should have no Rich formatting."""
    project = init_project(tmp_path)
    write_module(project, "context.py", VALID_CONTEXT)
    write_module(project, "plan.py", VALID_PLAN)
    result = generate_resume(project / ".stato")
    # No Rich markup
    assert "[bold]" not in result
    assert "[green]" not in result
