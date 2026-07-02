"""Tests for config-driven privacy scanning (WS10)."""
from stato.core.privacy import PrivacyScanner


def test_disable_by_id():
    content = 'email = "person@example.com"'
    default = PrivacyScanner()
    assert any(f.category == "pii" for f in default.scan_file("m.py", content))

    disabled = PrivacyScanner(disable=["email"])
    assert not disabled.scan_file("m.py", content)


def test_extra_pattern_dict():
    scanner = PrivacyScanner(extra_patterns=[
        {"pattern": r"LAB-\d{6}", "category": "pii",
         "description": "Lab sample id", "replacement": "{LAB_ID}"},
    ])
    findings = scanner.scan_file("m.py", "sample = LAB-123456")
    assert any(f.description == "Lab sample id" for f in findings)
    assert scanner.sanitize("sample = LAB-123456") == "sample = {LAB_ID}"


def test_from_config_reads_disable(tmp_path, monkeypatch):
    monkeypatch.setenv("STATO_CONFIG_DIR", str(tmp_path / "conf"))
    (tmp_path / ".stato").mkdir(parents=True)
    (tmp_path / ".stato" / "config.toml").write_text(
        "[privacy]\ndisable = [\"email\"]\n"
    )
    scanner = PrivacyScanner.from_config(tmp_path)
    assert not scanner.scan_file("m.py", 'x = "a@b.com"')


def test_from_config_reads_extra_patterns(tmp_path, monkeypatch):
    monkeypatch.setenv("STATO_CONFIG_DIR", str(tmp_path / "conf"))
    (tmp_path / ".stato").mkdir(parents=True)
    (tmp_path / ".stato" / "config.toml").write_text(
        "[privacy]\n"
        "extra_patterns = [\n"
        "  { pattern = 'ACME-[0-9]+', category = 'pii', "
        "description = 'Acme id', replacement = '{ACME}' },\n"
        "]\n"
    )
    scanner = PrivacyScanner.from_config(tmp_path)
    findings = scanner.scan_file("m.py", "id = ACME-42")
    assert any(f.description == "Acme id" for f in findings)


def test_default_patterns_still_present():
    scanner = PrivacyScanner()
    # a well-known secret shape is still caught
    findings = scanner.scan_file("m.py", "key = sk-ant-" + "a" * 30)
    assert any(f.category == "api_key" for f in findings)


def test_working_notes_in_crystallize_prompt():
    from stato.prompts import get_crystallize_prompt

    prompt = get_crystallize_prompt()
    assert "Working notes" in prompt
    assert "created_at" in prompt
    assert "__stato_type__" in prompt
