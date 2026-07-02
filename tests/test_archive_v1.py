"""Tests for archive format v1: format_version + checksums (WS4)."""
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import tomli
import tomli_w

from stato.core.composer import (
    ArchiveIntegrityError,
    graft,
    import_snapshot,
    inspect_archive,
    snapshot,
    verify_archive,
)
from stato.core.state_manager import init_project, write_module
from tests.fixtures import VALID_MEMORY, VALID_QC_SKILL


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    init_project(proj)
    write_module(proj, "skills/qc.py", VALID_QC_SKILL)
    write_module(proj, "memory.py", VALID_MEMORY)
    return proj


def _tamper(archive_path: Path, member: str, new_content: str):
    """Rewrite one member of a zip without updating the manifest."""
    with zipfile.ZipFile(archive_path) as zf:
        items = {n: zf.read(n) for n in zf.namelist()}
    items[member] = new_content.encode()
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, data in items.items():
            zf.writestr(n, data)


def test_snapshot_writes_v1_manifest(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    with zipfile.ZipFile(out) as zf:
        manifest = tomli.loads(zf.read("manifest.toml").decode())
    assert manifest["format_version"] == "1"
    assert "skills/qc.py" in manifest["checksums"]
    assert manifest["checksums"]["skills/qc.py"].startswith("sha256:")


def test_verify_ok(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    result = verify_archive(out)
    assert result["ok"] and not result["legacy"]
    assert result["format_version"] == "1"


def test_tampered_archive_detected(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    _tamper(out, "skills/qc.py", VALID_QC_SKILL + "\n# malicious addition\n")
    result = verify_archive(out)
    assert not result["ok"]
    assert result["mismatches"] == ["skills/qc.py"]


def test_import_refuses_tampered(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    _tamper(out, "skills/qc.py", VALID_QC_SKILL + "\n# malicious\n")
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ArchiveIntegrityError):
        import_snapshot(dest, out)
    assert not (dest / ".stato" / "skills" / "qc.py").exists()


def test_import_force_overrides(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    _tamper(out, "skills/qc.py", VALID_QC_SKILL + "\n# modified\n")
    dest = tmp_path / "dest"
    dest.mkdir()
    imported = import_snapshot(dest, out, force=True)
    assert "skills/qc.py" in imported


def test_graft_refuses_tampered(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    _tamper(out, "skills/qc.py", VALID_QC_SKILL + "\n# modified\n")
    dest = tmp_path / "dest"
    dest.mkdir()
    init_project(dest)
    result = graft(dest, out)
    assert not result.success
    assert any("integrity" in c for c in result.conflicts)


def test_legacy_archive_imports_with_warning(project, tmp_path):
    """A v0.5-style archive (no format_version) still imports."""
    legacy = tmp_path / "legacy.stato"
    manifest = {
        "name": "legacy",
        "description": "",
        "author": "",
        "created": datetime.now(timezone.utc).isoformat(),
        "stato_version": "0.5.0",
        "partial": False,
        "template": False,
        "included_modules": ["skills/qc.py"],
    }
    with zipfile.ZipFile(legacy, "w") as zf:
        zf.writestr("manifest.toml", tomli_w.dumps(manifest))
        zf.writestr("skills/qc.py", VALID_QC_SKILL)

    assert verify_archive(legacy)["legacy"] is True
    dest = tmp_path / "dest"
    dest.mkdir()
    imported = import_snapshot(dest, legacy)
    assert imported == ["skills/qc.py"]


def test_inspect_reports_integrity(project, tmp_path):
    out = snapshot(project, "test", output_path=tmp_path / "t.stato")
    info = inspect_archive(out)
    assert info["format_version"] == "1"
    assert info["integrity"]["ok"] is True


def test_registry_index_entry_and_download_verification(project, tmp_path):
    from stato.core.registry import RegistryPackage, file_sha256, make_index_entry

    out = snapshot(project, "pkgtest", output_path=tmp_path / "pkg.stato")
    entry = make_index_entry(out, url="https://x/pkg.stato", author="tester")
    assert "[packages.pkgtest]" in entry
    assert 'sha256 = "sha256:' in entry

    # download verification path (file:// URL)
    pkg = RegistryPackage(
        name="pkgtest", description="", author="t", url=out.as_uri(),
        version="1.0.0", tags=[], modules=2, updated="", sha256=file_sha256(out),
    )
    from stato.core.registry import download_package

    dl_dir = tmp_path / "dl"
    dl_dir.mkdir()
    downloaded = download_package(pkg, dl_dir)
    assert downloaded.exists()

    # corrupt expectation -> refuses
    pkg_bad = RegistryPackage(
        name="pkgtest2", description="", author="t", url=out.as_uri(),
        version="1.0.0", tags=[], modules=2, updated="",
        sha256="sha256:" + "0" * 64,
    )
    with pytest.raises(RuntimeError, match="checksum"):
        download_package(pkg_bad, dl_dir)
