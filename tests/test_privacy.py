"""
Privacy scanner tests. Pure Python, no LLM.
"""
from stato.core.privacy import PrivacyScanner


def test_detects_api_key():
    content = 'api_key = "sk-abc123def456ghi789jkl012mno345"'
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    assert len(findings) >= 1
    assert findings[0].category == "api_key"


def test_detects_aws_key():
    content = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    assert any(f.category == "credential" for f in findings)


def test_detects_home_path():
    content = 'data_path = "/home/niki/projects/data.h5ad"'
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    assert any(f.category == "path" for f in findings)


def test_detects_database_url():
    content = 'db = "postgres://admin:secretpass@db.internal:5432/mydb"'
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    assert any(f.category == "credential" for f in findings)


def test_detects_patient_id():
    content = 'patient_id = "P12345"'
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    assert any(f.category == "pii" for f in findings)


def test_sanitize_replaces_secrets():
    content = 'key = "sk-abc123def456ghi789jkl012mno345pqr"'
    scanner = PrivacyScanner()
    sanitized = scanner.sanitize(content)
    assert "sk-" not in sanitized
    assert "{API_KEY}" in sanitized


def test_sanitize_replaces_home_path():
    content = 'path = "/home/niki/data"'
    scanner = PrivacyScanner()
    sanitized = scanner.sanitize(content)
    assert "niki" not in sanitized
    assert "{user}" in sanitized


def test_clean_content_no_findings():
    content = '''
class QC:
    name = "qc_filtering"
    default_params = {"min_genes": 200}
    lessons_learned = "FFPE needs higher threshold"
'''
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    assert len(findings) == 0


def test_statoignore_loads(tmp_path):
    ignore_file = tmp_path / ".statoignore"
    ignore_file.write_text("*_TOKEN\n")
    scanner = PrivacyScanner(ignore_file=ignore_file)
    assert len(scanner.ignore_patterns) == 1


def test_sanitize_produces_clean_output():
    """Sanitized content should have no secrets."""
    content = '''
class Ctx:
    project = "test"
    description = "test"
    environment = {"api_key": "sk-abc123def456ghi789jkl012mno345pqr"}
    conventions = ["data lives at /home/niki/data"]
'''
    scanner = PrivacyScanner()
    sanitized = scanner.sanitize(content)
    assert "sk-" not in sanitized
    assert "niki" not in sanitized
    assert "{API_KEY}" in sanitized
    assert "{user}" in sanitized


def test_sanitize_preserves_structure():
    """Sanitized content should still be valid Python."""
    import ast

    content = '''
class Ctx:
    project = "test"
    description = "data at /home/niki/projects"
'''
    scanner = PrivacyScanner()
    sanitized = scanner.sanitize(content)
    # Should still parse as Python
    ast.parse(sanitized)  # should not raise


def test_findings_grouped_by_category():
    content = '''
key1 = "sk-abc123def456ghi789jkl012mno345pqr"
key2 = "AKIAIOSFODNN7EXAMPLE"
path = "/home/niki/data"
email = "user@example.com"
'''
    scanner = PrivacyScanner()
    findings = scanner.scan_file("test.py", content)
    categories = set(f.category for f in findings)
    assert "api_key" in categories
    assert "credential" in categories
    assert "path" in categories
    assert "pii" in categories
