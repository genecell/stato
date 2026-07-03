"""Tests for data model v2: provenance, __stato_type__, structured lessons,
strict/suppress (WS5)."""
from stato.core.compiler import validate
from stato.core.module import ModuleType

SKILL_WITH_PROVENANCE = '''
class BatchCorrection:
    """Batch effect correction."""
    name = "batch_correction"
    version = "1.0.0"
    created_at = "2026-05-01"
    updated_at = "2026-06-12"
    source = "debugging session 2026-06-12"
    confidence = 0.8
    used_in_steps = [3, 4]
    lessons = [
        {"condition": "n_batches > 5", "recommendation": "use harmony",
         "confidence": 0.9, "review_by": "2026-12-01"},
        {"recommendation": "always plot before/after UMAP"},
    ]

    def run(self):
        pass
'''


def test_provenance_fields_accepted():
    result = validate(SKILL_WITH_PROVENANCE, expected_type="skill")
    assert result.success
    assert not any(d.code == "E007" for d in result.hard_errors)
    cls = result.namespace["BatchCorrection"]
    assert cls.updated_at == "2026-06-12"
    assert cls.confidence == 0.8


def test_provenance_on_memory():
    source = '''
class ProjState:
    """Memory with provenance."""
    phase = "analysis"
    updated_at = "2026-07-01"
    source = "session recap"
'''
    result = validate(source)
    assert result.success
    assert result.module_type == ModuleType.MEMORY


def test_confidence_int_accepted_as_float():
    source = SKILL_WITH_PROVENANCE.replace("confidence = 0.8", "confidence = 1")
    result = validate(source, expected_type="skill")
    assert result.success


def test_confidence_out_of_range_advice():
    source = SKILL_WITH_PROVENANCE.replace("confidence = 0.8", "confidence = 5.0")
    result = validate(source, expected_type="skill")
    assert result.success  # advice only
    assert any(d.code == "I008" for d in result.advice)


def test_structured_lessons_valid_no_advice():
    result = validate(SKILL_WITH_PROVENANCE, expected_type="skill")
    assert not any(d.code == "I008" for d in result.advice)
    # I003 must NOT fire: structured lessons count as lessons
    assert not any(d.code == "I003" for d in result.advice)


def test_structured_lessons_malformed_advice():
    source = SKILL_WITH_PROVENANCE.replace(
        '{"recommendation": "always plot before/after UMAP"},',
        '"just a string",',
    )
    result = validate(source, expected_type="skill")
    assert result.success
    assert any(d.code == "I008" for d in result.advice)


def test_stato_type_overrides_inference():
    # Class name ends in State (would infer MEMORY) but declares context
    source = '''
class WeirdNameState:
    """Explicitly a context module."""
    __stato_type__ = "context"
    project = "demo"
    description = "explicit type declaration"
'''
    result = validate(source)
    assert result.success
    assert result.module_type == ModuleType.CONTEXT


def test_stato_type_invalid_value():
    source = '''
class Foo:
    """Bad declared type."""
    __stato_type__ = "wisdom"
    name = "foo"
'''
    result = validate(source)
    assert not result.success
    assert any(d.code == "E011" for d in result.hard_errors)


def test_stato_type_conflict_with_expected_warns():
    source = '''
class Foo:
    """Declared memory."""
    __stato_type__ = "memory"
    phase = "x"
'''
    result = validate(source, expected_type="context")
    assert result.success
    assert result.module_type == ModuleType.MEMORY
    assert any(d.code == "W008" for d in result.auto_corrections)


def test_skills_used_on_steps_validated():
    source = '''
class P:
    """Plan with skills_used."""
    name = "p"
    objective = "test"
    steps = [
        {"id": 1, "action": "a", "status": "pending", "skills_used": ["qc"]},
    ]
'''
    assert validate(source).success

    bad = source.replace('["qc"]', '"qc"')
    result = validate(bad)
    assert not result.success
    assert any(d.code == "E012" for d in result.hard_errors)


def test_strict_promotes_warnings_not_advice():
    # version = "1.0" triggers W003 (auto-correction warning)
    source = '''
class QC:
    """A skill with an advice-only gap and a warning."""
    name = "qc"
    version = "1.0"
    lessons_learned = "- something"

    def run(self):
        pass
'''
    normal = validate(source, expected_type="skill")
    assert normal.success
    strict = validate(source, expected_type="skill", strict=True)
    assert not strict.success  # W003 promoted


def test_strict_leaves_advice_advisory():
    # only advice (no docstring, no lessons, no type hints) — strict must NOT fail
    source = '''
class QC:
    name = "qc"

    def run(self):
        pass
'''
    strict = validate(source, expected_type="skill", strict=True)
    assert strict.success  # advice/info is not a correctness failure
    assert strict.advice


def test_error_codes_promotes_specific_code():
    source = '''
class QC:
    """Skill without type hints."""
    name = "qc"
    lessons_learned = "- x"

    def run(self):
        pass
'''
    assert validate(source, expected_type="skill").success
    promoted = validate(source, expected_type="skill", error_codes=["I006"])
    assert not promoted.success
    assert any(d.code == "I006" for d in promoted.hard_errors)


def test_suppress_hides_codes():
    source = '''
class QC:
    name = "qc"

    def run(self):
        pass
'''
    result = validate(source, expected_type="skill", suppress=["I002", "I003", "I006"])
    assert result.success
    assert not result.advice


def test_strict_plus_suppress_composes():
    source = '''
class QC:
    name = "qc"

    def run(self):
        pass
'''
    result = validate(
        source, expected_type="skill",
        strict=True, suppress=["I002", "I003", "I006"],
    )
    assert result.success
