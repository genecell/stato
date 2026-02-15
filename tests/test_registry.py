"""Tests for stato registry — search and package management."""
import tomli

from stato.core.registry import RegistryPackage, search_registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_search_by_name():
    packages = [
        RegistryPackage("scrna-expert", "scRNA-seq analysis", "genecell",
                        "", "1.0.0", ["bioinformatics", "scrna"], 5, ""),
        RegistryPackage("fastapi-expert", "FastAPI development", "user2",
                        "", "1.0.0", ["web", "api"], 3, ""),
    ]
    results = search_registry("scrna", packages)
    assert len(results) == 1
    assert results[0].name == "scrna-expert"


def test_search_by_tag():
    packages = [
        RegistryPackage("scrna-expert", "scRNA-seq analysis", "genecell",
                        "", "1.0.0", ["bioinformatics", "scanpy"], 5, ""),
        RegistryPackage("bulk-rna", "Bulk RNA-seq", "user2",
                        "", "1.0.0", ["bioinformatics", "deseq2"], 3, ""),
    ]
    results = search_registry("bioinformatics", packages)
    assert len(results) == 2


def test_search_by_description():
    packages = [
        RegistryPackage("qc-tools", "Quality control for sequencing data", "genecell",
                        "", "1.0.0", ["qc"], 2, ""),
    ]
    results = search_registry("sequencing", packages)
    assert len(results) == 1


def test_search_no_results():
    packages = [
        RegistryPackage("scrna-expert", "scRNA-seq", "genecell",
                        "", "1.0.0", ["bio"], 5, ""),
    ]
    results = search_registry("javascript", packages)
    assert len(results) == 0


def test_search_ranking():
    """Name match should rank higher than tag match."""
    packages = [
        RegistryPackage("python-testing", "Testing tools", "user1",
                        "", "1.0.0", ["python"], 3, ""),
        RegistryPackage("web-tools", "Web development", "user2",
                        "", "1.0.0", ["python", "web"], 4, ""),
    ]
    results = search_registry("python", packages)
    assert results[0].name == "python-testing"  # name match > tag match


def test_parse_registry_toml():
    """Test parsing a registry index TOML string."""
    toml_content = """
[meta]
version = 1

[packages.test-pkg]
description = "A test package"
author = "tester"
url = "https://example.com/test.stato"
version = "1.0.0"
tags = ["test"]
modules = 2
updated = "2026-01-01"
"""
    data = tomli.loads(toml_content)
    assert "test-pkg" in data["packages"]
    assert data["packages"]["test-pkg"]["version"] == "1.0.0"
    assert data["packages"]["test-pkg"]["modules"] == 2
