"""Tests for targeted module edits (WS3)."""
import pytest

from stato.core.compiler import validate
from stato.core.edits import EditError, append_lesson, set_plan_step

PLAN = '''
class ProjectPlan:
    """A plan."""
    name = "proj"
    objective = "ship it"
    decision_log = "chose X"
    steps = [
        {"id": 1, "action": "design", "status": "complete", "output": "spec"},
        {"id": 2, "action": "build", "status": "pending"},
        {"id": 3, "action": "test", "status": "pending"},
    ]
'''

SKILL = '''
class QC:
    """QC skill."""
    name = "qc"
    version = "1.0.0"
    lessons_learned = """
    - Existing lesson
    """
    def run(self):
        pass
'''

SKILL_NO_LESSONS = '''
class QC:
    """QC skill."""
    name = "qc"
    version = "1.0.0"
    def run(self):
        pass
'''


def _load(source, cls_name):
    from stato.core.astload import load_class

    return load_class(source)


def test_set_step_status():
    new = set_plan_step(PLAN, 2, status="complete", output="binary built")
    assert validate(new).success
    cls = _load(new, "ProjectPlan")
    step2 = next(s for s in cls.steps if s["id"] == 2)
    assert step2["status"] == "complete"
    assert step2["output"] == "binary built"


def test_set_step_status_only():
    new = set_plan_step(PLAN, 3, status="running")
    cls = _load(new, "ProjectPlan")
    step3 = next(s for s in cls.steps if s["id"] == 3)
    assert step3["status"] == "running"
    assert "output" not in step3


def test_set_step_preserves_others():
    new = set_plan_step(PLAN, 2, status="complete", output="x")
    cls = _load(new, "ProjectPlan")
    step1 = next(s for s in cls.steps if s["id"] == 1)
    assert step1["output"] == "spec"  # untouched
    assert len(cls.steps) == 3


def test_set_step_unknown_id_raises():
    with pytest.raises(EditError, match="no step with id 99"):
        set_plan_step(PLAN, 99, status="complete")


def test_set_step_result_revalidates():
    new = set_plan_step(PLAN, 2, status="complete", output="x")
    result = validate(new)
    assert result.success and result.module_type.value == "plan"


def test_append_lesson_keeps_existing():
    new = append_lesson(SKILL, "New insight about param tuning")
    assert validate(new).success
    cls = _load(new, "QC")
    assert "Existing lesson" in cls.lessons_learned
    assert "New insight about param tuning" in cls.lessons_learned


def test_append_lesson_creates_field():
    new = append_lesson(SKILL_NO_LESSONS, "First lesson")
    assert validate(new).success
    cls = _load(new, "QC")
    assert "First lesson" in cls.lessons_learned


def test_append_lesson_valid_skill():
    new = append_lesson(SKILL, "another")
    result = validate(new)
    assert result.success and result.module_type.value == "skill"


def test_edit_syntax_error_raises():
    with pytest.raises(EditError):
        set_plan_step("class Broken(:", 1, status="x")


def test_append_multiple_lessons():
    s = append_lesson(SKILL_NO_LESSONS, "one")
    s = append_lesson(s, "two")
    cls = _load(s, "QC")
    assert "one" in cls.lessons_learned and "two" in cls.lessons_learned
