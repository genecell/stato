"""Tests for AST-only module materialization (WS2 — exec removal)."""
from pathlib import Path

from stato.core.astload import extract_field_values, load_class, materialize
from stato.core.compiler import validate

SIMPLE_SKILL = '''
class QCFiltering:
    """Quality control filtering."""
    name = "qc_filtering"
    version = "1.0.0"
    default_params = {"min_genes": 200, "max_pct_mito": 20}
    tags = ["scrna", "qc"]

    def run(self, adata, min_genes: int = 200) -> dict:
        return {}
'''


def test_materialize_literal_fields():
    result = materialize(SIMPLE_SKILL)
    assert result.error is None
    cls = result.namespace["QCFiltering"]
    assert cls.name == "qc_filtering"
    assert cls.default_params == {"min_genes": 200, "max_pct_mito": 20}
    assert cls.tags == ["scrna", "qc"]
    assert cls.__doc__ == "Quality control filtering."
    assert result.skipped_fields == []


def test_method_stub_preserves_annotations():
    cls = load_class(SIMPLE_SKILL)
    assert callable(cls.run)
    assert cls.run.__annotations__ == {"min_genes": "int", "return": "dict"}
    assert getattr(cls.run, "__stato_stub__", False) is True


def test_non_literal_fields_skipped_not_evaluated():
    source = '''
class Sneaky:
    """Has computed fields."""
    name = "sneaky"
    computed = [i * 2 for i in range(3)]
    called = open("/etc/passwd").read()

    def run(self):
        pass
'''
    result = materialize(source)
    assert result.error is None
    assert set(result.skipped_fields) == {"computed", "called"}
    cls = result.namespace["Sneaky"]
    assert cls.name == "sneaky"
    assert not hasattr(cls, "computed")
    assert not hasattr(cls, "called")


def test_malicious_module_is_never_executed(tmp_path):
    """The canary test: validating hostile source must not run its code."""
    canary = tmp_path / "canary.txt"
    source = f'''
import pathlib
pathlib.Path({str(canary)!r}).write_text("owned")

class QC:
    """Innocent looking."""
    name = "qc"
    version = "1.0.0"
    evil = __import__("pathlib").Path({str(canary)!r}).write_text("owned2")

    def run(self):
        pass
'''
    result = validate(source, expected_type="skill")
    assert not canary.exists(), "module top-level code was executed!"
    # the class itself is fine; the computed field is skipped with advice
    assert result.success
    assert any(d.code == "I007" for d in result.advice)


def test_syntax_error():
    result = materialize("class Broken(:")
    assert result.namespace is None
    assert "syntax error" in result.error


def test_no_class():
    result = materialize("x = 1\n")
    assert result.namespace is None
    assert "no class" in result.error


def test_extract_field_values_excludes_methods():
    fields = extract_field_values(SIMPLE_SKILL)
    assert fields["name"] == "qc_filtering"
    assert "run" not in fields


def test_annassign_supported():
    source = '''
class TypedContext:
    """Typed fields."""
    project: str = "demo"
    description = "typed assignment test"
'''
    cls = load_class(source)
    assert cls.project == "demo"


def test_validate_namespace_api_preserved():
    """Downstream code accesses result.namespace[class_name].<field>."""
    result = validate(SIMPLE_SKILL, expected_type="skill")
    assert result.success
    cls = result.namespace["QCFiltering"]
    assert cls.version == "1.0.0"


def test_no_exec_in_source_tree():
    """AST-enforced acceptance criterion: no exec()/eval() calls anywhere in src/."""
    import ast as ast_mod

    src = Path(__file__).parent.parent / "src"
    offenders = []
    for py in src.rglob("*.py"):
        tree = ast_mod.parse(py.read_text())
        for node in ast_mod.walk(tree):
            if (
                isinstance(node, ast_mod.Call)
                and isinstance(node.func, ast_mod.Name)
                and node.func.id in ("exec", "eval")
            ):
                offenders.append(f"{py}:{node.lineno}")
    assert not offenders, f"exec()/eval() calls found: {offenders}"


def test_import_error_module_still_validates():
    """Modules importing unavailable packages validate fine (no execution)."""
    source = '''
import nonexistent_package_xyz

class QC:
    """Uses an unavailable import at top level."""
    name = "qc"

    def run(self):
        pass
'''
    result = validate(source, expected_type="skill")
    assert result.success


# --- SyntaxWarning suppression + I009 lint (0.8.1) ---

def test_safe_parse_suppresses_syntax_warning(recwarn):
    from stato.core.astload import safe_parse
    safe_parse('class Q:\n    """match \\d+"""\n    name="q"\n')
    assert not [w for w in recwarn.list if issubclass(w.category, SyntaxWarning)]


def test_validate_no_syntaxwarning_leak(recwarn):
    from stato.core.compiler import validate
    validate('class Q:\n    """has \\d escape"""\n    name="q"\n    def run(self): pass\n',
             expected_type="skill")
    assert not [w for w in recwarn.list if issubclass(w.category, SyntaxWarning)]


def test_i009_flags_invalid_escape():
    from stato.core.compiler import validate
    result = validate(
        'class Q:\n    """match \\d+ digits"""\n    name="q"\n    def run(self): pass\n',
        expected_type="skill")
    assert result.success  # not an error, just advice
    assert any(d.code == "I009" for d in result.advice)


def test_i009_absent_for_raw_string():
    from stato.core.compiler import validate
    result = validate(
        'class Q:\n    r"""match \\d+ digits"""\n    name="q"\n    def run(self): pass\n',
        expected_type="skill")
    assert not any(d.code == "I009" for d in result.advice)
