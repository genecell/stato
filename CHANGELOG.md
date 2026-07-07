# Changelog

All notable changes to Stato are documented here.

## [0.10.0] - 2026-07-07

Workspace — load only what the current task needs. 340 tests pass.

### Added
- **`stato workspace [TASK]`** and the MCP tool **`stato_workspace(task)`**:
  assemble a small, task-relevant working set of skills (projected to compact
  summaries) plus a one-line index of the rest to pull on demand. Inspired by
  the "global workspace" in LLMs — a small, capacity-limited, task-selected set
  broadcast to many uses.
  - **Live task query is the primary signal** (ranked via the lexical scorer);
    with no task it falls back to the **current plan step** (its `skills_used`,
    else its action + objective), then to index-only.
  - **Pins** ("directed modulation") are declared in the modules, not a sidecar:
    a skill `always_load = True`, or `context.pinned_skills = [...]`, always
    enter the working set. `--budget` / `--max-items` cap the rest (pins kept).
  - Stateless — recomputed each call.
- `team assemble` subagent bodies and `SKILL.md` now direct agents to call
  `stato_workspace(task)` — embedding the workspace in Claude Code (and subagent)
  workflows.

## [0.9.0] - 2026-07-03

Progressive disclosure — subagents that scale. 323 tests pass.

### Added — progressive disclosure
- **`core/summarize.py`**: a compact projection of a module — docstring, method
  signatures, params, tags, and a **lessons index** (one line per lesson).
  Because stato modules are AST-parseable, retrieval is precise (pull lesson N),
  not fuzzy — no embeddings.
- **`team assemble` now emits the lessons index + pull-on-demand by default**,
  so a subagent stays light instead of carrying whole skills. `--inline`
  embeds full skill source for environments without the MCP server. (Index size
  is roughly constant, so the token saving scales with skill size — ~45% on
  small skills, far more on large ones.)
- **MCP**: resource `stato://skills/{name}/summary` + tool
  `stato_get_skill_section(skill, id)` — a subagent reads the index and pulls
  the exact lesson **live** from the server (drift-free, precise).
- **`stato migrate-lessons`**: convert prose `lessons_learned` bullets into
  structured `lessons` entries (non-destructive), making each lesson
  individually addressable for precise pull.

### Changed
- `resume` warns when state files are ≥14 days old (staleness caveat, so an
  auto-restore doesn't confidently re-anchor to stale state).
- Reminder hook gains `[hooks] reminder_min_interval` — won't re-fire within N
  minutes even as steps accrue.

## [0.8.1] - 2026-07-03

Polish patch from real-project field feedback. 312 tests pass.

### Fixed
- **SyntaxWarning no longer pollutes output.** A stray `\d` in a non-raw user
  docstring made `ast.parse` emit a `SyntaxWarning` that leaked into
  `status`/`audit`/`resume`. All user-source parsing now routes through one
  `safe_parse` chokepoint that suppresses it.
- `hooks status` crashed on a `.claude/settings.json` that had no `hooks` key.

### Changed
- **`--strict` now promotes warnings only**, not advice/info — an existing
  project can adopt `--strict` without a type-hint sweep (I006 no longer fails
  every skill). New `--error-code` / `[validate] error_codes` promotes specific
  codes for granular strictness.
- `resume`/`status` show the running **Stato version**; `resume` warns on a
  **version mismatch** vs `context.environment` and shows filesystem-mtime
  freshness ("State files last modified").

### Added
- **`stato doctor`**: resolved binary path, version, `.stato/` presence, hooks
  status, MCP availability — and the PATH/env tip for conda/venv installs.
- **I009 authoring lint**: flags an invalid escape sequence in a non-raw string
  (suggests a raw string) at validation time.
- **Opt-in auto-stamp**: `[state] auto_stamp` (or `StateManager.write(stamp=)`)
  sets `updated_at` on write. Off by default to avoid diff churn.

## [0.8.0] - 2026-07-02

Make stato self-teaching to coding agents. 294 Tier 1 tests pass.

### Added — Agent Skill
- **`stato skill install`**: ships a canonical, spec-valid `SKILL.md` that
  teaches agents how to *use stato* (the operating loop, module schemas, key
  commands, MCP/hooks integration) and installs it into any tool's skills
  directory — `--tool claude|codex|cursor|gemini|all`, project or `--user`
  scope. The same portable Agent Skills file works across tools; only the
  target directory differs. `stato skill show` prints it.
- This is distinct from `stato bridge --platform skill`, which exports a
  *project's* captured expertise; the new skill documents the stato tool itself.
- Single source of truth (`skill_doc.py`); the repo's `skills/stato/SKILL.md`
  is generated from it and a test guards against drift. Frontmatter follows the
  Agent Skills spec (`name`/`description` required; `author`/`version` under
  `metadata`).

## [0.7.0] - 2026-07-02

Multi-agent teams and capture-quality tooling. 278 Tier 1 tests pass.

### Added — Team assembly
- **`stato team assemble`**: generate expertise-scoped subagents from
  `.stato/team.toml`. Each role gets only its skills (with optional transitive
  `with_deps`), keeping each subagent's context focused. Native output formats
  per tool: `claude` (`.claude/agents/*.md`), `gemini` (`.gemini/agents/*.md`),
  `codex` (`.codex/agents/*.toml`, prompt in `developer_instructions`), and
  `sdk` (`.stato/team/*.agent.json`). Handoffs render as prose (no enforced
  protocol); merge-not-overwrite, `--dry-run`, `--force`.

### Added — Quality & capture
- **`stato audit`**: score each module 0–10 with concrete gaps (missing
  lessons, undocumented params, absent provenance/confidence, stale `review_by`
  dates). `--json` and `--min SCORE` (exit 1 below threshold) for CI or
  pre-publish gating. Deterministic; AST-only.
- **Reminder hook**: `stato hooks install --reminders` adds a Stop-hook nudge
  that fires once when completed plan steps cross `[hooks] reminder_threshold`
  (default 3), then stays quiet until the next threshold. Non-blocking,
  watermark-based (Claude/Codex).
- **Granular MCP tools**: `stato_update_plan_step` and `stato_append_lesson`
  let an agent change one thing without regenerating a whole module — both
  validate-gated. Backed by `core/edits.py` (pure AST parse-modify-unparse).

### Fixed
- `.gitignore`: the `/*.stato` archive rule also matched the `.stato/` state
  directory (glob `*.stato` matches the name `.stato`), silently ignoring
  newly-added state files. Added `!/.stato`.

## [0.6.0] - 2026-07-02

The all-in-one upgrade: security hardening, live integration surfaces, and an
ecosystem-current bridge matrix. All 117 v0.5 Tier 1 tests still pass alongside
110+ new ones.

### Security
- **No more `exec()`**: module validation, resume, diff, and merge now build
  class objects purely from the AST (`ast.literal_eval`), so validating or
  importing a third-party archive can never execute its code. Non-literal
  fields degrade to advice (I007), never a crash. AST-enforced test guards it.
- **Archive integrity**: `.stato` archives are format v1 — the manifest carries
  `format_version` and per-module sha256 checksums. `import`/`graft`/`registry
  install` verify them and refuse tampered archives (`--force` to override).
  Legacy v0.5 archives still import (with a warning).
- Registry downloads verify sha256 when the index declares one; friendlier
  errors on malformed/unexpected index schema.

### Added — Hooks (compaction integration)
- `stato hooks install --platform claude|codex|gemini|all`: wires PreCompact /
  SessionStart (and platform equivalents) so validated `.stato/` state
  re-enters context after every compaction. Merge-not-overwrite, idempotent,
  `--dry-run`, `uninstall`, `status`. Gemini also gets an extension bundle
  (MCP server + `/stato:save`, `/stato:resume`).
- Opt-in freshness gate blocks auto-compaction when on-disk state is stale.
- `stato crystallize-transcript` (experimental): headless crystallization from
  a transcript via `claude -p`.

### Added — MCP server
- `stato mcp` (stdio): exposes state as resources (`stato://context|plan|memory|
  resume|skills|skills/{name}`), tools (`stato_validate`, `stato_write_module`
  with same-turn diagnostics, `stato_resume`, `stato_snapshot` with enforced
  privacy scan, `stato_registry_search`), and prompts (crystallize). One server
  serves every MCP client. Install with `pip install "stato[mcp]"`.
- `stato init --mcp` writes/merges a `.mcp.json` entry.

### Added — Bridges
- **AGENTS.md is now the primary bridge** (Linux Foundation standard). The old
  `codex` platform is an alias for the new `agents`.
- Cursor bridge emits `.cursor/rules/stato.mdc` with YAML frontmatter
  (`.cursorrules` is deprecated upstream; `cursor-legacy` still available).
- New platforms: `copilot` (`.github/copilot-instructions.md`), `gemini`
  (`GEMINI.md`), and `skill` (Agent Skills `SKILL.md` export).
- Bridge plugin architecture: custom platform specs from
  `<config>/bridges/*.py` when `[plugins] enabled = true`.
- Single bridge engine replaces four near-duplicate generators.

### Added — Config & data model
- Layered config: `~/.config/stato/config.toml` (XDG) + project
  `.stato/config.toml` + env (`STATO_REGISTRY_URL`, `STATO_CONFIG_DIR`).
  `stato config` shows effective values and their source; `--init` writes a
  template. Configurable: registry URL, privacy patterns, bridge defaults,
  validation strictness, history retention, freshness gate, plugins.
- Data model v2 (all optional, back-compat): `created_at`/`updated_at`/`source`
  on every type; skill `confidence`, `used_in_steps`, structured `lessons`;
  plan-step `skills_used`; explicit `__stato_type__` declaration.
- Privacy patterns are configurable (`[privacy] disable`, `extra_patterns`).

### Added — CLI/UX
- `--json` on status/validate/inspect/resume/diff/registry-search/find.
- Global `-q/--quiet`; `--dry-run` on snapshot/slice/graft; grouped `--help`.
- New `stato find` local lexical search; `stato registry package` generates a
  ready-to-PR index entry with checksum.
- Plain-English hint per error code.

### Reliability
- Writes are atomic (temp file + `os.replace`) and serialized across processes
  via an advisory lock; `.history/` pruned to `[history] keep` (default 50).

### Tooling
- `validate(strict=, suppress=)`; ruff + pytest-cov dev extras; GitHub Actions
  CI matrix (ubuntu/macos/windows × 3.10/3.12); version single-sourced from
  package metadata.

## [0.5.0] - 2026-02-15

### Added
- **Converter** (`stato convert`): Import from CLAUDE.md, .cursorrules, AGENTS.md, and SKILL.md files
- **Merger** (`stato merge`): Combine two .stato archives with conflict resolution (theirs/ours/newest/manual strategies)
- **Registry** (`stato registry`): Search, install, and list packages from GitHub-based package index
- Package metadata: authors, keywords, classifiers, project URLs in pyproject.toml
- LICENSE file (MIT)

### Changed
- `stato crystallize` now saves to file by default (`.stato/prompts/crystallize.md`), `--print` flag for terminal output
- `stato bridge` detects existing files and warns before overwrite (interactive prompt with o/a/s/c options)
- Bridge `write()` returns `tuple[Path, str]` (path, action)
- Version references use `__version__` from package instead of hardcoded strings

## [0.4.0] - 2026-02-13

### Added
- **Resume** (`stato resume`): Structured recap of project state for context restoration
- **Privacy Scanner** (`stato snapshot --sanitize`): 19 regex patterns across 6 categories, interactive review gate
- **Differ** (`stato diff`): Field-by-field module comparison, snapshot diff, backup diff
- `.statoignore` template created by `stato init`

## [0.3.0] - 2026-02-12

### Added
- **Bundle Parser** (`stato import-bundle`): AST-based parser for web AI bundle files
- **Web Crystallize** (`stato crystallize --web`): Prompt template for web AI conversations
- Bridge generators for all 4 platforms (claude, cursor, codex, generic)

## [0.2.0] - 2026-02-11

### Changed
- Renamed package from `agentstate` to `stato`
- Archive extension changed from `.agent` to `.stato`
- State directory changed from `.agentstate/` to `.stato/`

## [0.1.0] - 2026-02-10

### Added
- Initial release
- 7-pass graduated compiler with 10 error codes and 6 auto-corrections
- State manager with validate-then-write invariant and `.history/` backup
- Composer: snapshot, import, inspect, slice, graft operations
- CLI with core commands: init, validate, status, snapshot, import, inspect, slice, graft, bridge, crystallize
- 4 module types: skill, plan, memory, context
