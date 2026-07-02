"""Tests for the shared lexical search scorer (WS4/WS7)."""
from stato.core.registry import RegistryPackage, search_registry
from stato.core.search import score_text, search_items


def test_exact_token_match():
    assert score_text("filtering", "QC filtering for scRNA") == 1.0


def test_multi_term_requires_both():
    both = score_text("batch effect", "batch effect correction")
    one = score_text("batch effect", "batch normalization")
    assert both > one > 0


def test_fuzzy_typo_match():
    assert score_text("filterng", "qc filtering") > 0


def test_substring_credit():
    assert score_text("scrna", "scrna-seq analysis toolkit") == 1.0
    assert 0 < score_text("norm", "normalization") <= 1.0


def test_no_match_zero():
    assert score_text("kubernetes", "single cell qc filtering") == 0.0


def test_search_items_weights_and_order():
    items = [
        {"name": "qc_filtering", "description": "quality control", "tags": ["qc"]},
        {"name": "normalize", "description": "qc mentioned in passing", "tags": []},
    ]
    results = search_items("qc", items, {"name": 3.0, "description": 2.0, "tags": 1.0})
    assert results[0][1]["name"] == "qc_filtering"


def test_registry_search_uses_scorer():
    packages = [
        RegistryPackage(
            name="scrna-expert", description="single cell RNA analysis",
            author="a", url="", version="1.0.0", tags=["scrna", "qc"],
            modules=3, updated="",
        ),
        RegistryPackage(
            name="webdev-kit", description="frontend tooling",
            author="b", url="", version="1.0.0", tags=["react"],
            modules=2, updated="",
        ),
    ]
    results = search_registry("single cell", packages)
    assert results and results[0].name == "scrna-expert"
    assert all(p.name != "webdev-kit" for p in results)
