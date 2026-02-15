"""
Compiler validation tests. Pure Python, no LLM.
Run after EVERY change: pytest tests/test_compiler.py
"""
from stato.core.compiler import validate
from stato.core.module import ModuleType
from stato.core.state_manager import init_project, write_module, rollback
from tests.fixtures import (
    VALID_QC_SKILL,
    VALID_PLAN,
    VALID_MEMORY,
    VALID_CONTEXT,
    CORRUPTED_SKILL_MISSING_FIELDS,
    CORRUPTED_SKILL_BAD_TYPES,
    FIXABLE_SKILL,
)


# --- Valid modules pass ---

def test_valid_skill_passes():
    result = validate(VALID_QC_SKILL, expected_type="skill")
    assert result.success
    assert result.module_type == ModuleType.SKILL
    assert len(result.hard_errors) == 0


def test_valid_plan_passes():
    result = validate(VALID_PLAN, expected_type="plan")
    assert result.success
    assert result.module_type == ModuleType.PLAN


def test_valid_memory_passes():
    result = validate(VALID_MEMORY, expected_type="memory")
    assert result.success


def test_valid_context_passes():
    result = validate(VALID_CONTEXT, expected_type="context")
    assert result.success


# --- Hard errors ---

def test_syntax_error_rejected():
    result = validate("class Foo:\n    x = [1, 2,", expected_type="skill")
    assert not result.success
    assert any(d.code == "E001" for d in result.hard_errors)


def test_no_class_rejected():
    result = validate("x = 42\ny = 'hello'", expected_type="skill")
    assert not result.success
    assert any(d.code == "E002" for d in result.hard_errors)


def test_missing_name_rejected():
    result = validate(CORRUPTED_SKILL_MISSING_FIELDS, expected_type="skill")
    assert not result.success
    assert any(d.code == "E003" for d in result.hard_errors)


def test_missing_run_method_rejected():
    source = '''
class QC:
    name = "qc"
    # no run() method
'''
    result = validate(source, expected_type="skill")
    assert not result.success
    assert any(d.code == "E004" for d in result.hard_errors)


def test_bad_field_types_rejected():
    result = validate(CORRUPTED_SKILL_BAD_TYPES, expected_type="skill")
    assert not result.success
    assert any(d.code == "E007" for d in result.hard_errors)


def test_plan_circular_dependency_rejected():
    source = '''
class BadPlan:
    name = "circular"
    objective = "test"
    steps = [
        {"id": 1, "action": "a", "status": "pending", "depends_on": [2]},
        {"id": 2, "action": "b", "status": "pending", "depends_on": [1]},
    ]
'''
    result = validate(source, expected_type="plan")
    assert not result.success
    assert any(d.code == "E009" for d in result.hard_errors)


def test_plan_missing_dependency_target_rejected():
    source = '''
class BadPlan:
    name = "bad_dep"
    objective = "test"
    steps = [
        {"id": 1, "action": "a", "status": "pending", "depends_on": [99]},
    ]
'''
    result = validate(source, expected_type="plan")
    assert not result.success
    assert any(d.code == "E008" for d in result.hard_errors)


def test_plan_invalid_status_rejected():
    source = '''
class BadPlan:
    name = "bad_status"
    objective = "test"
    steps = [
        {"id": 1, "action": "a", "status": "vibing"},
    ]
'''
    result = validate(source, expected_type="plan")
    assert not result.success
    assert any(d.code == "E010" for d in result.hard_errors)


def test_plan_duplicate_step_id_rejected():
    source = '''
class BadPlan:
    name = "dup_id"
    objective = "test"
    steps = [
        {"id": 1, "action": "a", "status": "pending"},
        {"id": 1, "action": "b", "status": "pending"},
    ]
'''
    result = validate(source, expected_type="plan")
    assert not result.success


# --- Auto-corrections ---

def test_string_depends_on_autocorrected():
    result = validate(FIXABLE_SKILL, expected_type="skill")
    assert result.success
    assert any(d.code == "W001" for d in result.auto_corrections)
    # Corrected source should have list
    ns = result.namespace
    assert isinstance(ns["QC"].depends_on, list)


def test_version_missing_patch_autocorrected():
    result = validate(FIXABLE_SKILL, expected_type="skill")
    assert result.success
    assert any(d.code == "W003" for d in result.auto_corrections)


# --- Advice ---

def test_missing_docstring_advice():
    source = '''
class QC:
    name = "qc"
    @staticmethod
    def run(**kwargs): pass
'''
    result = validate(source, expected_type="skill")
    assert result.success  # advice never blocks
    assert any(d.code == "I002" for d in result.advice)


def test_missing_lessons_learned_advice():
    source = '''
class QC:
    """QC skill."""
    name = "qc"
    @staticmethod
    def run(**kwargs): pass
'''
    result = validate(source, expected_type="skill")
    assert result.success
    assert any(d.code == "I003" for d in result.advice)


# --- State manager integration ---

def test_write_valid_module_succeeds(tmp_path):
    project = init_project(tmp_path)
    result = write_module(project, "skills/qc.py", VALID_QC_SKILL)
    assert result.success
    assert (project / ".stato/skills/qc.py").exists()


def test_write_invalid_module_rejected(tmp_path):
    project = init_project(tmp_path)
    result = write_module(project, "skills/qc.py", CORRUPTED_SKILL_MISSING_FIELDS)
    assert not result.success
    assert not (project / ".stato/skills/qc.py").exists()


def test_write_creates_backup(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    # Write again (update)
    updated = VALID_QC_SKILL.replace('version = "1.2.0"', 'version = "1.3.0"')
    write_module(project, "skills/qc.py", updated)
    # Backup should exist
    history_dir = project / ".stato/.history"
    assert history_dir.exists()
    backups = list(history_dir.glob("qc.*.py"))
    assert len(backups) >= 1


def test_rollback_restores_previous(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    updated = VALID_QC_SKILL.replace('version = "1.2.0"', 'version = "1.3.0"')
    write_module(project, "skills/qc.py", updated)

    current = (project / ".stato/skills/qc.py").read_text()
    assert "1.3.0" in current

    rollback(project, "skills/qc.py")
    restored = (project / ".stato/skills/qc.py").read_text()
    assert "1.2.0" in restored
