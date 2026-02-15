"""Bundle parser and import-bundle roundtrip tests."""
from pathlib import Path

from stato.core.bundle import parse_bundle, BundleParseResult
from stato.core.state_manager import init_project, write_module


def test_parse_bundle_extracts_skills(tmp_path):
    bundle = tmp_path / "test_bundle.py"
    bundle.write_text('''
SKILLS = {
    "qc": \'\'\'
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = []
    @staticmethod
    def run(**kwargs): pass
\'\'\',
    "norm": \'\'\'
class Norm:
    name = "norm"
    version = "1.0.0"
    depends_on = []
    @staticmethod
    def run(**kwargs): pass
\'\'\',
}
''')
    result = parse_bundle(bundle)
    assert len(result.skills) == 2
    assert "qc" in result.skills
    assert "norm" in result.skills
    assert len(result.errors) == 0


def test_parse_bundle_extracts_plan(tmp_path):
    bundle = tmp_path / "test_bundle.py"
    bundle.write_text("""
PLAN = \'\'\'
class MyPlan:
    name = "test"
    objective = "test"
    steps = [{"id": 1, "action": "test", "status": "pending"}]
\'\'\'
""")
    result = parse_bundle(bundle)
    assert result.plan is not None
    assert "MyPlan" in result.plan


def test_parse_bundle_extracts_all_types(tmp_path):
    bundle = tmp_path / "test_bundle.py"
    bundle.write_text("""
SKILLS = {
    "qc": \'\'\'
class QC:
    name = "qc"
    @staticmethod
    def run(**kwargs): pass
\'\'\',
}

PLAN = \'\'\'
class P:
    name = "p"
    objective = "test"
    steps = [{"id": 1, "action": "a", "status": "pending"}]
\'\'\'

MEMORY = \'\'\'
class M:
    phase = "planning"
\'\'\'

CONTEXT = \'\'\'
class C:
    project = "test"
    description = "test project"
\'\'\'
""")
    result = parse_bundle(bundle)
    assert len(result.skills) == 1
    assert result.plan is not None
    assert result.memory is not None
    assert result.context is not None


def test_parse_bundle_syntax_error(tmp_path):
    bundle = tmp_path / "bad_bundle.py"
    bundle.write_text("SKILLS = {broken syntax here")
    result = parse_bundle(bundle)
    assert len(result.errors) > 0


def test_parse_bundle_empty_file(tmp_path):
    bundle = tmp_path / "empty.py"
    bundle.write_text("# empty bundle\nx = 42\n")
    result = parse_bundle(bundle)
    assert len(result.skills) == 0
    assert result.plan is None


def test_import_bundle_roundtrip(tmp_path):
    """Full roundtrip: bundle -> import -> validate -> read back."""
    bundle = tmp_path / "bundle.py"
    bundle.write_text("""
SKILLS = {
    "qc": \'\'\'
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"min_genes": 200}
    @staticmethod
    def run(**kwargs): pass
\'\'\',
}

PLAN = \'\'\'
class P:
    name = "test_plan"
    objective = "test roundtrip"
    steps = [{"id": 1, "action": "qc", "status": "pending"}]
\'\'\'
""")

    project = tmp_path / "project"
    project.mkdir()
    init_project(project)

    result = parse_bundle(bundle)
    assert len(result.skills) == 1

    # Write skill
    write_result = write_module(project, "skills/qc.py", result.skills["qc"])
    assert write_result.success

    # Write plan
    write_result = write_module(project, "plan.py", result.plan)
    assert write_result.success

    # Verify files exist
    assert (project / ".stato" / "skills" / "qc.py").exists()
    assert (project / ".stato" / "plan.py").exists()
