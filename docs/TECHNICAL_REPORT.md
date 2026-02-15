# Stato: Technical Report
## Portable AI Agent Expertise Through Validated Composition

**Version:** 0.5.0
**Date:** February 2026
**Authors:** Min Dai

---

### Abstract

Stato is a Python framework that solves the agent amnesia problem: AI coding agents lose learned expertise between sessions, across platforms, and after context compaction. Stato captures agent knowledge as validated Python modules, composes them into portable archives, and generates lightweight bridge files that restore expertise into any supported platform. The system includes a 7-pass graduated compiler, a privacy scanner for safe export, and a novel web-AI-to-coding-agent transfer pipeline. Testing across 115 structural tests demonstrates reliable operation across all subsystems.

---

### 1. Introduction

Modern AI coding agents (Claude Code, Cursor, GitHub Codex) learn significant domain knowledge during work sessions: parameter thresholds that work for specific datasets, architectural decisions and their rationale, lessons from debugging failures. This knowledge is lost when:

1. **Sessions end** — no persistence mechanism exists beyond manually editing `CLAUDE.md` or `.cursorrules`
2. **Context is compacted** — the `/compact` operation summarizes conversation history, discarding detailed expertise
3. **Platforms change** — expertise learned in Claude Code cannot transfer to Cursor or Codex
4. **Web AI conversations end** — knowledge developed in Claude.ai, Gemini, or ChatGPT stays trapped in chat logs

Existing solutions are insufficient. Manual `CLAUDE.md` files are unvalidated free text that grows stale. Platform-specific memory features are siloed and non-portable. Prompt engineering frameworks operate at the prompt level, not the expertise level.

Stato takes a different approach: expertise is structured as Python classes with compiler-validated fields, composed into portable archives using a formal algebra (snapshot, slice, graft), and projected into platform-specific bridge files that guide agent behavior. A bundle import system enables transferring expertise from web AI conversations into coding agent projects without requiring the web AI to run any tools.

---

### 2. Architecture

Stato consists of seven subsystems organized in a layered architecture. The module system provides the data model. The compiler validates it. The state manager persists it. The composer enables portability. The bridge generator connects to platforms. The privacy scanner ensures safe export. The bundle parser enables web AI transfer.

#### 2.1 Module System

Stato defines five module types, each a Python class with structured fields:

| Type | Purpose | Required Fields | Required Methods |
|------|---------|----------------|-----------------|
| **Skill** | Reusable expertise with parameters and lessons | `name` | `run()` |
| **Plan** | Step-by-step execution tracking with DAG dependencies | `name`, `objective`, `steps` | — |
| **Memory** | Working state: current phase, known issues, reflection | `phase` | — |
| **Context** | Project metadata: datasets, environment, conventions | `project`, `description` | — |
| **Protocol** | Multi-agent handoff schemas | `name`, `handoff_schema` | — |

The key design decision is using Python classes rather than JSON, YAML, or TOML. This choice has three advantages: (1) the agent's tool already parses Python, so modules ARE executable code; (2) narrative fields like `lessons_learned` coexist naturally with structured fields like `default_params`; (3) type inference from class structure eliminates the need for explicit type declarations.

A typical skill module:

```python
class QualityControl:
    """QC filtering for scRNA-seq data."""
    name = "qc_filtering"
    version = "1.2.0"
    depends_on = ["scanpy"]
    default_params = {
        "min_genes": 200,
        "max_genes": 5000,
        "max_pct_mito": 20,
        "min_cells": 3,
    }
    lessons_learned = """
    - Cortex tissue: max_pct_mito=20 retains ~85% of cells
    - FFPE samples: increase to max_pct_mito=40
    - Mouse data: use mt- prefix (lowercase). Human: MT-
    """
    @staticmethod
    def run(adata_path, **kwargs):
        params = {**QualityControl.default_params, **kwargs}
        return params
```

Each module type has a schema defined in `core/module.py` that maps field names to expected Python types. The schemas are intentionally minimal — they enforce structural correctness without constraining content.

#### 2.2 Graduated Compiler

The compiler (`core/compiler.py`) implements a 7-pass validation pipeline with three severity tiers:

- **Hard errors** (E-codes): block the write entirely
- **Auto-corrections** (W-codes): fixable issues applied automatically
- **Advice** (I-codes): suggestions that don't block

The seven passes execute in order with early termination:

| Pass | Name | Purpose | Terminates on Failure |
|------|------|---------|----------------------|
| 1 | Syntax | `ast.parse()` — catches malformed Python | Yes |
| 2 | Structure | Finds primary class, checks for docstring | Yes |
| 3 | Type Inference | Determines module type from class name and fields | No |
| 4 | Schema Check | Verifies required fields and methods exist | Yes |
| 5 | Type Check | Validates field types, applies auto-corrections | Yes |
| 6 | Execute | Runs source in sandbox, verifies methods are callable | Yes |
| 7 | Semantic | Module-specific validation (DAG acyclicity for plans) | No |

Pass 5 implements three auto-corrections that fix common issues without user intervention:

- **W001**: `depends_on = "scanpy"` (string) → `depends_on = ["scanpy"]` (list)
- **W002**: `depends_on = 42` (int) → `depends_on = [42]` (list)
- **W003**: `version = "1.0"` → `version = "1.0.0"` (adds patch number)

Corrections are applied in reverse line order to avoid offset drift when modifying source text. The corrected source is stored in `ValidationResult.corrected_source` and used for subsequent passes.

Pass 7 performs semantic validation specific to each module type. For plans, this includes: step ID uniqueness (E008), dependency reference validity (E008), status value validation against the allowed set `{pending, running, complete, failed, blocked}` (E010), and DAG acyclicity checking via DFS with three-color marking (E009).

The complete error code catalog:

| Code | Severity | Description |
|------|----------|-------------|
| E001 | Error | Syntax error |
| E002 | Error | No class definition found |
| E003 | Error | Missing required field |
| E004 | Error | Missing required method |
| E005 | Error | Runtime execution error |
| E006 | Error | Required method not callable |
| E007 | Error | Field type mismatch |
| E008 | Error | Plan: duplicate step ID or invalid dependency reference |
| E009 | Error | Plan: circular dependency in step DAG |
| E010 | Error | Plan: invalid step status value |
| W001 | Warning | `depends_on` string auto-wrapped in list |
| W002 | Warning | `depends_on` int auto-wrapped in list |
| W003 | Warning | Version missing patch number, auto-fixed |
| W004 | Warning | Plan step missing status, auto-set to pending |
| W005 | Warning | Multiple classes found, using first |
| W006 | Warning | Cannot confidently infer module type |
| I001 | Info | Class name doesn't follow naming convention |
| I002 | Info | No docstring on class |
| I003 | Info | No `lessons_learned` on skill |
| I004 | Info | No `decision_log` on plan |
| I006 | Info | `run()` has no type hints |

#### 2.3 State Manager

The state manager (`core/state_manager.py`) enforces the **validate-then-write invariant**: no module reaches disk without passing the compiler. The write path is:

1. Validate source through the 7-pass pipeline
2. If existing file, create timestamped backup in `.stato/.history/`
3. Write the (possibly auto-corrected) source to the target path
4. Return the `ValidationResult` for caller inspection

Backups use a simple naming scheme: `{module_stem}.{timestamp}.py`. Rollback reads the most recent backup and rewrites the current file. This zero-dependency approach (no git required, no database) ensures stato works in any environment.

The `init_project()` function creates the directory structure:

```
project/
  .stato/
    skills/          # Skill modules
    .history/        # Automatic backups
    prompts/         # Crystallize prompt templates
      crystallize.md
      crystallize_web.md
  .statoignore       # Privacy scan exclusion patterns
```

#### 2.4 Composition Engine

The composer (`core/composer.py`) implements four operations that form an algebra over module collections:

**Snapshot** creates a `.stato` archive (ZIP with `manifest.toml`):
- Discovers all modules via `_discover_modules()`
- Applies optional filtering by module name, type, or exclusion list
- Optionally applies template reset (clears runtime state, preserves expertise)
- Optionally sanitizes via the privacy scanner
- Writes `manifest.toml` + module files into a ZIP archive

**Import** extracts modules from a `.stato` archive into a project, with optional filtering by module name or type.

**Slice** extracts specific modules with dependency awareness. When `--with-deps` is set, it performs BFS through the dependency graph, automatically including transitive dependencies and emitting warnings about what was auto-included.

**Graft** adds external modules with conflict detection. When a name collision occurs, the caller chooses from four strategies: `ask` (report conflict), `replace` (overwrite), `rename` (append `_imported` suffix), or `skip` (ignore).

The archive format uses POSIX paths (`PurePosixPath`) internally for cross-platform compatibility and TOML for the manifest to keep it human-readable.

#### 2.5 Bridge Generator

The bridge generator produces platform-specific files that serve as a lightweight index (~500 tokens) pointing agents to detailed module files. Each bridge follows the same pattern:

1. Scan `.stato/` for all valid modules
2. Build a skill summary table (name, version, key parameters, lesson count)
3. Summarize plan progress (objective, completed/total steps, next step)
4. Append working rules that guide agent behavior

Four bridge implementations share a common base class (`BridgeBase`):

| Platform | Output File | Section Header |
|----------|------------|----------------|
| Claude Code | `CLAUDE.md` | Working Rules |
| Cursor | `.cursorrules` | Rules |
| Codex | `AGENTS.md` | Working Rules |
| Generic | `README.stato.md` | Guidelines |

The working rules instruct agents to: (1) read the plan first, (2) read relevant skills before acting, (3) update plan status after completing steps, (4) add new lessons to skill files, (5) validate after changes, (6) fix validation errors before proceeding, (7) update memory before stopping, and (8) run `stato resume` when context feels stale.

This on-demand loading design keeps the bridge under 500 tokens. Agents read full skill files only when performing that specific task, avoiding the context window bloat that occurs when all expertise is embedded in a single file.

#### 2.6 Privacy Scanner

The privacy scanner (`core/privacy.py`) detects sensitive content before export. It searches for 19 patterns across six categories:

| Category | Examples | Replacement |
|----------|----------|-------------|
| `api_key` | `sk-...`, `sk-ant-...` | `{API_KEY}` |
| `credential` | AWS keys, database URLs, private keys, passwords | `{AWS_ACCESS_KEY}`, `{DATABASE_URL}` |
| `token` | GitHub PATs, Slack tokens, Bearer tokens | `{GITHUB_TOKEN}`, `{TOKEN}` |
| `path` | `/home/user/...`, `/Users/user/...` | `/home/{user}/...` |
| `network` | Internal IPs (10.x.x.x, 192.168.x.x) | `{INTERNAL_IP}` |
| `pii` | Email addresses, patient IDs, SSNs | `{EMAIL}`, `{SUBJECT_ID}` |

The scanner includes bioinformatics-specific patterns (patient IDs, medical record numbers) reflecting stato's origins in scientific computing workflows.

Key design principle: **sanitize-on-export, never modify originals**. The `sanitize()` method returns a new string with replacements applied. Original files on disk are never modified by the privacy scanner.

The `.statoignore` file supports pattern-based suppression for known false positives, following a format similar to `.gitignore`.

The snapshot command integrates the scanner through an interactive review gate. When findings are detected and no `--sanitize` or `--force` flag is passed, the user sees a grouped summary and four choices: sanitize (auto-replace), review (see full detail then decide), force (export as-is with warning), or cancel.

#### 2.7 Bundle Import (Web AI Bridge)

The bundle system solves a specific problem: web AIs (Claude.ai, Gemini, ChatGPT) can generate structured code but cannot run CLI tools. The solution is a two-step workflow:

1. **Crystallize** (in web AI): paste the `stato crystallize --web` prompt, which asks the AI to output a single Python file (`stato_bundle.py`) containing all expertise as string variables
2. **Import** (in coding agent): run `stato import-bundle stato_bundle.py` to parse, validate, and write the modules

The bundle format:

```python
SKILLS = {
    "skill_name": '''
class SkillName:
    name = "skill_name"
    version = "1.0.0"
    ...
''',
}

PLAN = '''
class AnalysisPlan:
    name = "plan_name"
    ...
'''

MEMORY = '''...'''
CONTEXT = '''...'''
```

The bundle parser (`core/bundle.py`) uses `ast.parse()` to safely extract variable values without executing the untrusted file. It walks the AST, finds assignments to `SKILLS`, `PLAN`, `MEMORY`, and `CONTEXT`, and extracts their string literal values. This approach is secure — no code from the bundle file is ever executed during parsing.

After parsing, each extracted module is validated through the full 7-pass compiler before being written to disk via the state manager, maintaining the validate-then-write invariant.

---

### 3. Cross-Platform Strategy

Stato uses the file system as a universal interface. Every supported platform has a convention for project-level instruction files:

- Claude Code reads `CLAUDE.md`
- Cursor reads `.cursorrules`
- Codex reads `AGENTS.md`

These are ordinary files that the agent discovers automatically. Stato generates them as lightweight indexes that point to `.stato/` for detailed content.

The token cost model is efficient:

| Component | Approximate Tokens |
|-----------|-------------------|
| Bridge file | ~500 |
| Each skill (on demand) | ~300-500 |
| Plan module | ~200-400 |
| Memory + Context | ~200-300 |

An agent performing a specific task reads the bridge (~500 tokens) plus the relevant skill (~400 tokens), totaling ~900 tokens of expertise context. This is far less than embedding all expertise inline, which would scale linearly with the number of skills.

The bridge file is regenerated on demand via `stato bridge`, ensuring it always reflects the current state of `.stato/`. Agents are instructed via working rules to run `stato validate .stato/` after making changes, which keeps the feedback loop tight.

---

### 4. Stato as Persistent Memory

Context compaction (`/compact`) is a lossy operation. When an agent's context window fills, the system summarizes the conversation history to free space. This summarization discards specific details: parameter values that worked, error messages that were diagnosed, architectural decisions and their rationale.

Stato modules survive compaction because they are files on disk, not conversation content. The crystallize-compact-resume cycle works as follows:

1. **Before compacting**: the agent (or user) runs `stato crystallize` and captures key expertise into `.stato/` modules
2. **During compaction**: conversation history is summarized, but `.stato/` files remain intact
3. **After compaction**: the agent runs `stato resume` to get a structured recap of project state, or the bridge file (`CLAUDE.md`) already points to the surviving modules

The `stato resume` command reads all modules and produces a structured recap covering project context, plan progress with completed step outputs, available skills with parameters and lesson counts, and memory state including known issues and reflections. A `--brief` mode compresses this to a single paragraph for quick orientation.

Comparison of memory approaches:

| Approach | Validated | Portable | Survives Compact | Structured |
|----------|-----------|----------|-------------------|------------|
| Manual `CLAUDE.md` | No | No | Yes (file) | No |
| `/compact` summary | No | No | No (lossy) | No |
| Platform memory | No | No | Varies | Varies |
| Stato modules | Yes (compiler) | Yes (archives) | Yes (files) | Yes (schema) |

Limitations: the agent must cooperate by actually writing to `.stato/` modules. Crystallization quality depends on prompt quality and the agent's willingness to follow instructions. Stato validates format, not semantic correctness — a `lessons_learned` field with "todo: add lessons" will pass validation.

---

### 5. Empirical Validation

#### 5.1 A/B Test: Fresh vs Expert Agent

To validate that stato transfers meaningful expertise, we conducted a qualitative comparison:

- **Session A** (no stato): Asked Claude Code "How does stato's compiler validate modules?" from a fresh session. The agent gave generic advice about multi-pass validation.
- **Session B** (with stato): Same question, but with `.stato/` modules containing the actual compiler's architecture. The agent correctly described the specific 7-pass pipeline, named error codes (E001-E010), explained auto-corrections (W001-W003 with the reverse-line-order application strategy), and referenced the validate-then-write invariant.

The qualitative difference was clear: Session B's responses contained specific, accurate implementation details that Session A could not know.

#### 5.2 Web AI to Coding Agent Transfer

The bundle import pipeline was tested end-to-end:

1. A Claude.ai conversation about scRNA-seq analysis was crystallized using the web crystallize prompt
2. The resulting `stato_bundle.py` was imported via `stato import-bundle`
3. A fresh Claude Code session with the imported modules correctly referenced tissue-specific parameters and analysis decisions from the original web conversation

This demonstrates that expertise transfer across platform boundaries is achievable through stato's bundle mechanism.

#### 5.3 Test Suite

Stato maintains a two-tier test strategy:

- **Tier 1** (115 tests, zero cost): structural tests covering the compiler, state manager, composer, privacy scanner, differ, bundle parser, resume, converter, merger, registry, and bridge generators. All tests run in under 11 seconds using `pytest tests/ -m "not agent"`.
- **Tier 2** (subscription cost): behavioral tests via `claude-agent-sdk` that verify end-to-end agent interactions.

Test distribution by file:

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_compiler.py` | 21 | Validation pipeline, write/rollback |
| `test_structural.py` | 25 | Init, snapshot, import, slice, graft, bridge, crystallize |
| `test_privacy.py` | 12 | Detection patterns, sanitization, category grouping |
| `test_resume.py` | 7 | Resume generation, brief mode, empty project handling |
| `test_bundle.py` | 6 | Bundle parsing, roundtrip import |
| `test_diff.py` | 4 | Module diff, snapshot diff, backup diff |

---

### 6. Related Work

| System | Focus | How Stato Differs |
|--------|-------|-------------------|
| **SkillKit** | Prompt templates | Stato validates skills, not just templates. Modules have structure, versioning, and dependencies. |
| **MemGPT/Letta** | Long-term memory via memory management | Stato is file-based and platform-agnostic. No server required. |
| **Voyager (Minecraft)** | Skill library for game agents | Stato is general-purpose and cross-platform, not game-specific. |
| **LangGraph** | Agent orchestration graphs | Stato manages expertise, not execution flow. Complementary. |
| **CrewAI** | Multi-agent coordination | Stato focuses on expertise persistence, not agent communication. Protocol modules are planned for future handoff support. |
| **Custom GPTs** | Platform-specific agent configuration | Stato is open, portable, and composable. No vendor lock-in. |
| **CLAUDE.md** (manual) | Project-level agent instructions | Stato adds validation, versioning, composition, privacy scanning, and cross-platform bridges. |

---

### 7. Limitations and Future Work

#### Limitations

1. **Agent cooperation required**: Stato cannot force an agent to read or write modules. The agent must follow the working rules in the bridge file.
2. **Crystallization quality varies**: The quality of captured expertise depends on the crystallize prompt and the agent's response. Poor crystallization produces modules that pass validation but contain little useful content.
3. **Format validation, not semantic validation**: The compiler verifies that `lessons_learned` is a string, not that it contains useful lessons. Semantic quality assessment is out of scope.
4. **Write-then-read model**: There is no real-time streaming or live synchronization between agents. Modules are written, then read by the next session.
5. **Stale state after branch changes**: If the user switches git branches, `.stato/` may contain state from a different branch. No branch-awareness mechanism exists.
6. **Single-agent focus**: The current system is designed for one agent working on one project. Multi-agent scenarios require the planned Protocol module type and merge operation.

#### Future Work

- **Merge operation**: Combine expertise from multiple agents or branches, with field-level conflict resolution
- **Multi-agent team assembly**: Use Protocol modules to define handoff schemas between specialized agents
- **Community registry**: Search and install shared skill modules (e.g., `stato install bioinformatics/qc_filtering`)
- **MCP server**: Deeper platform integration via the Model Context Protocol, enabling agents to call stato operations directly
- **Automatic crystallization triggers**: File watchers or git hooks that prompt crystallization at natural stopping points
- **Quality scoring**: Heuristic assessment of `lessons_learned` content quality (length, specificity, actionability)

---

### 8. Conclusion

Stato addresses a genuine gap in the AI agent tooling ecosystem: validated, composable, cross-platform agent expertise. By treating expertise as structured Python modules rather than free-text instructions, stato enables a level of reliability (compiler validation), portability (archive composition), and safety (privacy scanning) that manual approaches cannot achieve.

The web AI bridge is a unique contribution. No existing tool enables structured expertise transfer from web AI conversations (Claude.ai, Gemini, ChatGPT) into coding agent projects. The bundle format — safe AST parsing of a single Python file — makes this transfer possible without requiring the web AI to run any tools.

The competitive window for tools in this space is estimated at 12-18 months before platform vendors implement proprietary solutions. Stato's open-source, minimal-dependency design positions it as an interoperability layer that remains valuable even as platforms add native memory features.

Stato works today, with 75 passing tests, 13 CLI commands, support for three major coding agent platforms, and a web AI transfer pipeline. It is available as a Python package installable via `pip install stato`.

---

### Appendix A: CLI Command Reference

| Command | Description | Key Options |
|---------|-------------|-------------|
| `stato init` | Initialize `.stato/` project structure | `--path` |
| `stato validate <target>` | Run 7-pass compiler on module(s) | — |
| `stato status` | Show all modules and plan progress | `--path` |
| `stato snapshot` | Export as `.stato` archive | `--name`, `--template`, `--module`, `--type`, `--exclude`, `--sanitize`, `--force` |
| `stato import <archive>` | Import from `.stato` archive | `--module`, `--type`, `--as`, `--dry-run`, `--platform` |
| `stato import-bundle <file>` | Import from web AI bundle | `--platform`, `--dry-run` |
| `stato inspect <archive>` | Preview archive contents | — |
| `stato slice` | Extract specific modules | `--module`, `--with-deps`, `--output`, `--name` |
| `stato graft <source>` | Add external module | `--module`, `--as`, `--on-conflict` |
| `stato bridge` | Generate platform bridge file | `--platform` (`claude`, `cursor`, `codex`, `generic`, `auto`, `all`) |
| `stato crystallize` | Print expertise capture prompt | `--raw`, `--web` |
| `stato diff` | Compare modules or snapshots | `--brief` |
| `stato resume` | Generate project state recap | `--raw`, `--brief` |

### Appendix B: Error Code Catalog

**Hard Errors (block write):**

| Code | Message |
|------|---------|
| E001 | Syntax error: `{details}` |
| E002 | No class definition found |
| E003 | Missing required field: `{field}` |
| E004 | Missing required method: `{method}()` |
| E005 | Runtime execution error: `{type}: {message}` |
| E006 | Required method `{method}()` is not callable |
| E007 | Field `{field}` expects `{expected}`, got `{actual}` |
| E008 | Duplicate step ID / dependency references nonexistent step |
| E009 | Circular dependency in plan step DAG |
| E010 | Invalid step status `{status}` |

**Auto-Corrections (applied automatically):**

| Code | Action |
|------|--------|
| W001 | `depends_on` string wrapped in list |
| W002 | `depends_on` int wrapped in list |
| W003 | Version patch number appended (`"1.0"` → `"1.0.0"`) |
| W004 | Missing step status set to `"pending"` |
| W005 | Multiple classes found, using first |
| W006 | Module type inference uncertain, defaulting |

**Advice (informational):**

| Code | Suggestion |
|------|------------|
| I001 | Class name doesn't follow naming convention |
| I002 | No docstring on class |
| I003 | No `lessons_learned` on skill |
| I004 | No `decision_log` on plan |
| I006 | `run()` has no type hints |

### Appendix C: Module Schema Reference

**Skill Module:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique skill identifier |
| `version` | `str` | No | Semantic version (`"1.2.0"`) |
| `depends_on` | `list` | No | Dependencies (other skill names or packages) |
| `default_params` | `dict` | No | Default parameter values |
| `lessons_learned` | `str` | No | Markdown-formatted lessons from experience |
| `description` | `str` | No | Short description |
| `input_schema` | `dict` | No | Expected input format |
| `output_schema` | `dict` | No | Expected output format |
| `tags` | `list` | No | Categorization tags |
| `context_requires` | `list` | No | Required context fields |
| `run()` | method | Yes | Execution entry point |

**Plan Module:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Plan identifier |
| `objective` | `str` | Yes | What this plan achieves |
| `steps` | `list[dict]` | Yes | Step dicts with `id`, `action`, `status`, optional `output`, `depends_on` |
| `version` | `str` | No | Plan version |
| `decision_log` | `str` | No | Record of key decisions |
| `constraints` | `list` | No | Constraints on execution |
| `created_by` | `str` | No | Author attribution |

Step status values: `pending`, `running`, `complete`, `failed`, `blocked`.

**Memory Module:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phase` | `str` | Yes | Current work phase |
| `tasks` | `list` | No | Active task list |
| `known_issues` | `dict` | No | Known problems and descriptions |
| `reflection` | `str` | No | Agent's current understanding |
| `error_history` | `list` | No | Record of errors encountered |
| `decisions` | `list` | No | Decisions made |
| `metadata` | `dict` | No | Arbitrary metadata |
| `last_updated` | `str` | No | Timestamp |

**Context Module:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project` | `str` | Yes | Project name |
| `description` | `str` | Yes | Project description |
| `datasets` | `list` | No | Data file paths |
| `environment` | `dict` | No | Tool versions |
| `conventions` | `list` | No | Project conventions |
| `tools` | `list` | No | Required tools |
| `pending_tasks` | `list` | No | Incomplete tasks |
| `completed_tasks` | `list` | No | Finished tasks |
| `team` | `list` | No | Team members |
| `notes` | `str` | No | Free-form notes |

**Protocol Module:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Protocol identifier |
| `handoff_schema` | `dict` | Yes | Schema for agent-to-agent handoff |
| `description` | `str` | No | Protocol description |
| `validation_rules` | `list` | No | Rules for validating handoff data |
| `error_handling` | `str` | No | Error handling strategy |
