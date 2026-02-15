# Stato Testing Guide

## Overview

Tests are split into two tiers with different cost profiles:

- **Tier 1** — Pure Python structural and compiler tests. No LLM calls, no tokens consumed, runs in under a second. Run these after every change.
- **Tier 2** — Agent behavioral tests using real Claude Code sessions via `claude-agent-sdk`. Uses subscription tokens. Run these only at milestones.

The default `pytest` configuration runs only Tier 1 tests (via `addopts = "-m 'not agent'"` in `pyproject.toml`).

---

## Tier 1: Free Tests

### What they test

Tier 1 tests cover the entire codebase without making any LLM calls:

- **Compiler validation** — every error code (E001–E010), auto-correction (W001–W006), and advice code (I001–I006)
- **State manager** — validate-gated writes, backup creation, rollback
- **Composer** — snapshot/import roundtrips, template resets, partial exports, inspect, slice, graft
- **Bridge generators** — CLAUDE.md, .cursorrules, AGENTS.md content and token efficiency
- **Privacy scanner** — secret detection, PII patterns, sanitization, .statoignore
- **Differ** — module comparison, snapshot diff, backup diff
- **Bundle parser** — bundle extraction, roundtrip import, error handling

### How to run

```bash
# Default — runs only Tier 1 (same as pytest -m "not agent")
pytest

# Verbose with test names
pytest -v

# Specific test file
pytest tests/test_compiler.py -v

# Specific test
pytest tests/test_compiler.py::test_plan_circular_dependency_rejected -v

# Short tracebacks on failure
pytest -v --tb=short
```

### Test files

#### `tests/test_compiler.py` — 21 tests

Compiler validation pipeline and state manager integration.

| Test | What it verifies |
|---|---|
| `test_valid_skill_passes` | Valid skill module passes all 7 passes |
| `test_valid_plan_passes` | Valid plan module passes |
| `test_valid_memory_passes` | Valid memory module passes |
| `test_valid_context_passes` | Valid context module passes |
| `test_syntax_error_rejected` | E001: syntax errors caught in Pass 1 |
| `test_no_class_rejected` | E002: files without classes rejected |
| `test_missing_name_rejected` | E003: missing required field detected |
| `test_missing_run_method_rejected` | E004: missing required method detected |
| `test_bad_field_types_rejected` | E007: type mismatches caught (e.g., `depends_on = 42`) |
| `test_plan_circular_dependency_rejected` | E009: circular step dependencies caught |
| `test_plan_missing_dependency_target_rejected` | E008: references to nonexistent steps caught |
| `test_plan_invalid_status_rejected` | E010: invalid status values caught |
| `test_plan_duplicate_step_id_rejected` | Duplicate step IDs caught |
| `test_string_depends_on_autocorrected` | W001: `"scanpy"` auto-wrapped to `["scanpy"]` |
| `test_version_missing_patch_autocorrected` | W003: `"1.0"` auto-fixed to `"1.0.0"` |
| `test_missing_docstring_advice` | I002: advice emitted but doesn't block |
| `test_missing_lessons_learned_advice` | I003: advice emitted but doesn't block |
| `test_write_valid_module_succeeds` | Valid module writes to disk |
| `test_write_invalid_module_rejected` | Invalid module does NOT write to disk |
| `test_write_creates_backup` | Updating a module creates a backup in `.history/` |
| `test_rollback_restores_previous` | Rollback restores the previous version |

#### `tests/test_structural.py` — 24 tests

File operations, archive management, bridge generation, and CLI integration.

| Test | What it verifies |
|---|---|
| `test_init_creates_directory_structure` | `init` creates `.stato/` and `skills/` |
| `test_init_writes_crystallize_prompt` | `init` writes crystallize.md prompt template |
| `test_snapshot_creates_valid_archive` | Snapshot produces a zip with manifest and all modules |
| `test_partial_snapshot_type_filter` | `--type skill` exports only skills |
| `test_partial_snapshot_exclude` | `--exclude memory` omits memory modules |
| `test_partial_snapshot_single_module` | `--module skills/qc` exports only that module |
| `test_import_roundtrip_preserves_content` | Snapshot → import preserves content exactly |
| `test_template_resets_plan_preserves_expertise` | Template mode resets steps to pending, keeps lessons |
| `test_partial_import_single_module` | Import one module from a multi-module archive |
| `test_inspect_shows_archive_contents` | Inspect returns module list without extracting |
| `test_graft_conflict_detection` | Grafting same-named module detects collision |
| `test_slice_warns_missing_dependency` | Slicing without deps warns about missing dependencies |
| `test_slice_with_deps_includes_dependencies` | `--with-deps` auto-includes dependency modules |
| `test_bridge_generates_claude_md` | CLAUDE.md contains skill names and parameters |
| `test_bridge_token_efficiency` | CLAUDE.md stays under 800 tokens with 15 skills |
| `test_cursor_bridge_generates_cursorrules` | Cursor bridge generates .cursorrules |
| `test_codex_bridge_generates_agents_md` | Codex bridge generates AGENTS.md |
| `test_bridge_all_generates_all_platforms` | `--platform all` generates all bridge files |
| `test_crystallize_cli_raw` | `crystallize --raw` prints prompt as plain text |
| `test_crystallize_cli_rich` | `crystallize` uses Rich formatting |
| `test_crystallize_shows_subtitle` | `crystallize` shows subtitle in panel |
| `test_crystallize_web_raw` | `crystallize --web --raw` prints web prompt |
| `test_crystallize_web_rich` | `crystallize --web` uses Rich formatting |
| `test_init_writes_web_crystallize_prompt` | `init` writes crystallize_web.md prompt template |

#### `tests/test_privacy.py` — 9 tests

Privacy scanner for detecting secrets, PII, and sensitive paths.

| Test | What it verifies |
|---|---|
| `test_detects_api_key` | Catches API key patterns |
| `test_detects_aws_key` | Catches AWS access key patterns |
| `test_detects_home_path` | Catches home directory paths |
| `test_detects_database_url` | Catches database connection strings |
| `test_detects_patient_id` | Catches PII patterns |
| `test_sanitize_replaces_secrets` | `--sanitize` replaces secrets with placeholders |
| `test_sanitize_replaces_home_path` | `--sanitize` replaces home paths |
| `test_clean_content_no_findings` | Clean content passes with no findings |
| `test_statoignore_loads` | `.statoignore` patterns suppress false positives |

#### `tests/test_diff.py` — 4 tests

Module and snapshot comparison.

| Test | What it verifies |
|---|---|
| `test_diff_detects_version_change` | Detects version field changes between modules |
| `test_diff_detects_param_change` | Detects parameter changes between modules |
| `test_diff_snapshots` | Compares two .stato archives for added/removed/changed |
| `test_diff_no_backup_returns_empty` | No backup returns empty diff |

#### `tests/test_bundle.py` — 6 tests

Bundle parser and import-bundle roundtrip.

| Test | What it verifies |
|---|---|
| `test_parse_bundle_extracts_skills` | Extracts multiple skills from SKILLS dict |
| `test_parse_bundle_extracts_plan` | Extracts PLAN string constant |
| `test_parse_bundle_extracts_all_types` | Extracts SKILLS + PLAN + MEMORY + CONTEXT |
| `test_parse_bundle_syntax_error` | Bad syntax returns errors list |
| `test_parse_bundle_empty_file` | Empty/irrelevant file returns empty result |
| `test_import_bundle_roundtrip` | Parse → write_module → verify files on disk |

### Total: 64 tests, < 3 seconds

---

## Tier 2: Agent Behavioral Tests

### What they test

Tier 2 tests verify the core promise: does expertise actually transfer to a Claude Code session? They spin up real Claude Code sessions using `claude-agent-sdk` and check that the agent uses learned parameters, references lessons, and continues from the correct plan step.

### Prerequisites

```bash
pip install -e ".[test-agent]"
```

This installs `claude-agent-sdk` and `anyio`. Requires an active Claude Code login.

### How to run

```bash
# Run only Tier 2 tests
pytest -m agent -v

# Run just the core promise test (cheapest check)
pytest tests/test_agent_behavior.py::TestCorePromise -m agent -v
```

### Token cost

- Single test: ~20–40K subscription tokens
- Full Tier 2 suite: ~100–200K subscription tokens

### When to run

Run Tier 2 tests only at milestones:

- After the compiler is fully working
- After snapshot/import is working
- After bridge generation is working
- After the full CLI is working

Do NOT run after every small edit.

### Status

The `agent` marker is defined in `pyproject.toml` and excluded by default via `addopts`. The Tier 2 test file (`tests/test_agent_behavior.py`) is planned for Phase 2 — once the package has been validated on real projects.

---

## Running Tests — Command Reference

| Command | What it runs | Cost |
|---|---|---|
| `pytest` | Tier 1 only (default) | Free |
| `pytest -v` | Tier 1, verbose | Free |
| `pytest -m agent` | Tier 2 only | ~100–200K tokens |
| `pytest -m "agent or not agent"` | Everything | ~100–200K tokens |
| `pytest tests/test_compiler.py` | Compiler tests only | Free |
| `pytest tests/test_structural.py` | Structural tests only | Free |
| `pytest tests/test_privacy.py` | Privacy scanner tests only | Free |
| `pytest tests/test_diff.py` | Diff tests only | Free |
| `pytest tests/test_bundle.py` | Bundle parser tests only | Free |
| `pytest -v --tb=short` | Verbose, short tracebacks | Free |
| `pytest -x` | Stop on first failure | Free |

---

## Test Fixtures

All test data lives in `tests/fixtures.py`. Each fixture is a multiline string containing a complete Python module.

| Fixture | Module Type | Purpose |
|---|---|---|
| `VALID_QC_SKILL` | Skill | QC filtering with params and lessons_learned |
| `VALID_NORMALIZE_SKILL` | Skill | Normalization with dependency on `qc_filtering` |
| `VALID_CLUSTER_SKILL` | Skill | Clustering with resolution params |
| `VALID_PLAN` | Plan | 7-step analysis pipeline, 3 complete, 4 pending |
| `VALID_MEMORY` | Memory | Analysis state with known issues and reflection |
| `VALID_CONTEXT` | Context | Project config with datasets and conventions |
| `CORRUPTED_SKILL_MISSING_FIELDS` | Skill (invalid) | Missing `name` and `run()` — triggers E003, E004 |
| `CORRUPTED_SKILL_BAD_TYPES` | Skill (invalid) | `depends_on = 42`, `default_params = "not a dict"` — triggers E007 |
| `FIXABLE_SKILL` | Skill (auto-correctable) | `version = "1.0"`, `depends_on = "scanpy"` — triggers W001, W003 |

The `tests/conftest.py` file provides:
- A `project` fixture that creates an initialized stato project in a temp directory
- A `load_module()` helper that execs a module file and returns its primary class

---

## Adding New Tests

### Conventions

1. **Import fixtures** from `tests/fixtures.py` — don't inline large module strings
2. **Use `tmp_path`** (pytest built-in) for any test that writes files
3. **Use `init_project(tmp_path)`** to set up a project directory
4. **Assert on `ValidationResult` fields**: `result.success`, `result.hard_errors`, `result.auto_corrections`, `result.advice`, `result.module_type`
5. **Check diagnostic codes** with `any(d.code == "E003" for d in result.hard_errors)`

### Example: adding a new compiler test

```python
# tests/test_compiler.py

def test_plan_multiple_running_steps_rejected():
    source = '''
class BadPlan:
    name = "multi_running"
    objective = "test"
    steps = [
        {"id": 1, "action": "a", "status": "running"},
        {"id": 2, "action": "b", "status": "running"},
    ]
'''
    result = validate(source, expected_type="plan")
    # Add assertion based on expected behavior
    assert result.success or not result.success  # adjust to match actual rule
```

### Example: adding a new structural test

```python
# tests/test_structural.py

def test_snapshot_with_description(tmp_path):
    """Snapshot manifest includes the description field."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)

    archive = snapshot(project, name="described", description="My expert system")
    manifest = _load_manifest(archive)
    assert manifest["description"] == "My expert system"
```

### Adding a new fixture

Add the module source string to `tests/fixtures.py`, then import it in your test file.
