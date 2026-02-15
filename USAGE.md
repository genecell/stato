# Stato Usage Guide

## Getting Started

### Initializing a project

```bash
stato init
```

This creates the directory structure:

```
.stato/
├── skills/       # Skill modules go here
├── .history/     # Automatic backups on every write
└── prompts/      # Crystallize prompt templates
```

Use `--path` to initialize in a different directory:

```bash
stato init --path ~/my-project
```

### Crystallizing expertise

Already have a project with expertise accumulated in chat history, code comments, or your head? Three commands:

```bash
pip install stato
stato init
stato crystallize
```

The `crystallize` command saves a prompt to `.stato/prompts/crystallize.md` that instructs your coding agent to examine your existing project and capture its expertise into stato modules. Tell your agent: "Read and follow `.stato/prompts/crystallize.md`".

**Flags:**

- `--print` : also print the full prompt to terminal
- `--web` : prompt for web AI conversations (prints to terminal, saves to `crystallize_web.md`)
- `--path` : project directory (default: `.`)

### What the agent will do

When given the crystallize prompt, your coding agent will:

1. **Create skill modules** in `.stato/skills/`, with learned parameters, lessons, and dependencies
2. **Create a plan module** in `.stato/plan.py`, marking completed and pending steps
3. **Create a memory module** in `.stato/memory.py`, recording phase, tasks, and known issues
4. **Create a context module** in `.stato/context.py`, documenting conventions, datasets, and tools
5. **Validate everything** by running `stato validate .stato/`

The agent writes modules from its own context. No manual module writing needed.

### Writing modules manually

Create `.stato/skills/qc.py`:

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
    - If retention < 60%, thresholds are probably too aggressive
    """
    @staticmethod
    def run(adata_path, **kwargs):
        params = {**QualityControl.default_params, **kwargs}
        return params
```

Modules are Python classes. Structured fields (name, version, depends_on, default_params) are compiler-validated. Narrative fields (lessons_learned) are presence-validated only. Methods (run) must be callable.

### Validating modules

```bash
stato validate .stato/
```

Validate a single file:

```bash
stato validate .stato/skills/qc.py
```

Output shows each module with PASS/FAIL, its detected type, any errors, auto-corrections, and advice:

```
  PASS qc.py  (skill)
    W001 depends_on is string, auto-wrapping in list (auto-fixed)
    W003 Version missing patch number, auto-fixing: '1.0' -> '1.0.0' (auto-fixed)
    I003 No lessons_learned on skill

All 1 module(s) valid.
```

Auto-corrections are applied automatically. Hard errors block the write entirely. Advice is informational only.

### Checking project status

```bash
stato status
```

Shows a table of all modules with their type, class name, and version. If a plan module exists, it also shows a progress panel with the objective, completion count, and next step.

---

## Across Sessions

The primary use case: your agent's knowledge persists between sessions on disk.

### Generating a bridge

After crystallizing or writing modules, generate a bridge file so your coding agent discovers the expertise automatically:

```bash
stato bridge --platform claude
```

Claude Code auto-reads `CLAUDE.md` at the start of every session. The bridge contains:
- A skill summary table (name, version, key parameters, lesson count)
- Current plan progress (objective, completion, next step)
- Working rules for the agent

The bridge is a table of contents, not the full expertise. The agent loads individual skill files on demand (~500 tokens each) only when needed.

### Session resume

Restore agent context after `/compact` or at the start of a new session:

```bash
stato resume
```

Reads all modules and produces a structured recap: project context, plan progress, skills with parameters, and memory state.

```bash
stato resume --brief    # one-paragraph summary
stato resume --raw      # plain text, pipeable
```

### The session workflow

```bash
# Session 1: set up
stato init
stato crystallize
# Saves prompt to .stato/prompts/crystallize.md
# Tell your agent: "Read and follow .stato/prompts/crystallize.md"

stato validate .stato/
stato bridge --platform claude

# Session 2 (next day, after /compact, new terminal):
# Agent reads CLAUDE.md automatically
stato resume             # structured recap if needed

# Agent works, learns new things, updates modules
stato validate .stato/   # verify after changes
```

### How bridge working rules work

| Rule | Purpose |
|---|---|
| Read plan first | Agent resumes from correct step, not from the beginning |
| Read skill files before tasks | Agent uses learned parameters, not generic defaults |
| Update plan after steps | Progress is tracked, next session continues correctly |
| Update lessons_learned | Knowledge accumulates across sessions |
| Run validation after changes | Compiler catches corruption before it compounds |
| Fix errors before proceeding | Never work on top of invalid state |

---

## Across Projects

Transfer expertise between projects, teammates, or the community.

### Full snapshot

Export all modules as a `.stato` archive:

```bash
stato snapshot --name "scrna-expert"
```

Creates `scrna-expert.stato`, a zip file containing `manifest.toml` and all module `.py` files.

### Template mode

Use `--template` to create a reusable starting point:

```bash
stato snapshot --name "scrna-template" --template
```

Template mode applies these resets:

| Module Type | What resets | What's preserved |
|---|---|---|
| **Skill** | Nothing | Everything (skills ARE the expertise) |
| **Plan** | All step statuses -> `"pending"`, `output` fields removed | `decision_log`, step structure, `depends_on` |
| **Memory** | `phase` -> `"init"`, `error_history` cleared, `reflection` -> `prior_reflection` | Task list, known issues |
| **Context** | Nothing | Everything (conventions, tools are reusable) |

### Partial export

```bash
stato snapshot --name "skills-only" --type skill         # export only skills
stato snapshot --name "qc-only" --module skills/qc       # export a single module
stato snapshot --name "no-memory" --exclude memory       # exclude memory
```

The `--module`, `--type`, and `--exclude` flags can be combined. Archives created with any filter are marked `partial: true` in the manifest.

### Inspecting an archive

Preview what's inside without importing:

```bash
stato inspect scrna-expert.stato
```

Shows archive metadata (name, creation date, template flag) and a table of included modules with their types and validation status.

### Importing

Import all modules from an archive:

```bash
stato import scrna-expert.stato
```

Import into a specific project:

```bash
stato import scrna-expert.stato --path ~/new-project
```

Import a single module:

```bash
stato import full-export.stato --module skills/qc
```

Preview import:

```bash
stato import full-export.stato --dry-run
```

### Slicing modules

Extract specific modules from your project into a new archive:

```bash
stato slice --module skills/normalize
```

If the sliced module has `depends_on` referencing another module in the project, you'll see a warning. To automatically include dependencies:

```bash
stato slice --module skills/normalize --with-deps
```

### Grafting modules

Add a module from an external archive or `.py` file:

```bash
stato graft expert.stato --module skills/clustering
```

#### Conflict handling

If a module with the same name already exists, stato detects the conflict. Control behavior with `--on-conflict`:

```bash
stato graft expert.stato --module skills/qc --on-conflict replace   # replace existing
stato graft expert.stato --module skills/qc --on-conflict rename    # auto-rename
stato graft expert.stato --module skills/qc --on-conflict skip      # skip silently
```

The default (`--on-conflict ask`) reports the conflict without writing.

### Merging archives

Combine two archives with conflict resolution:

```bash
stato merge a.stato b.stato --output combined.stato
```

Strategies: `--strategy union` (default), `--strategy prefer-left`, `--strategy prefer-right`.

Use `--dry-run` to preview what would be merged without writing.

---

## Across Platforms

Same expertise, different coding agents. One command generates all bridges.

### Supported platforms

| Platform | Bridge file | Auto-read by agent? |
|---|---|---|
| Claude Code | `CLAUDE.md` | Yes |
| Cursor | `.cursorrules` | Yes |
| Codex | `AGENTS.md` | Yes |
| Generic | `README.stato.md` | Agent must be told to read it |

### Generating bridges

```bash
stato bridge --platform claude     # Claude Code
stato bridge --platform cursor     # Cursor
stato bridge --platform codex      # Codex
stato bridge --platform generic    # Any agent
stato bridge --platform all        # All of the above
```

### Example CLAUDE.md output

Given a project with a QC skill and an analysis plan:

```markdown
# Stato Project

This project uses Stato for structured expertise management.
All agent state lives in .stato/ as validated Python modules.

## Available Skills
| Skill | Version | Key Parameters | Lessons |
|---|---|---|---|
| qc_filtering | v1.2.0 | min_genes=200, max_genes=5000, max_pct_mito=20 | 4 lessons |

Read .stato/skills/<name>.py for full details when needed.

## Current Plan
Objective: Complete scRNA-seq analysis pipeline
Progress: 3/7 steps complete
Current step: Step 4 -- find_hvg (pending)
Full plan: .stato/plan.py

## Working Rules
1. Read .stato/plan.py FIRST to understand current progress
2. Read relevant skill files BEFORE performing that task
3. After completing a step, update plan.py: status -> "complete", add output
4. If you learn something new, add to the skill's lessons_learned
5. Run `stato validate .stato/` after any changes
6. If validation fails, fix errors before proceeding
```

---

## Web AI Bridge

Web AIs (Claude.ai, Gemini, ChatGPT) can't run CLI tools, but they can output Python. The bundle workflow bridges the gap with one file and one command.

### Step 1: Get the prompt

```bash
stato crystallize --web | pbcopy
```

This prints the web AI prompt to terminal (and copies it to clipboard). The prompt tells the web AI to output a `stato_bundle.py` file containing all the expertise from your conversation. The prompt is also saved to `.stato/prompts/crystallize_web.md`.

### Step 2: Paste into the web AI

Paste the prompt into your Claude.ai, Gemini, or ChatGPT conversation. The AI will output a single Python file with `SKILLS`, `PLAN`, `MEMORY`, and `CONTEXT` variables, each containing a stato module as a triple-quoted string.

Save the output as `stato_bundle.py` in your project directory.

### Step 3: Import the bundle

```bash
stato import-bundle stato_bundle.py
```

This parses the bundle, validates each module, writes them to `.stato/`, and generates a bridge file. Your coding agent now has the expertise from the web AI conversation.

**Options:**

- `--platform all` : generate bridges for all platforms (Claude, Cursor, Codex, Generic)
- `--dry-run` : parse and validate without writing files

### The bundle file format

A bundle is a plain Python file with specific variable names:

```python
# stato_bundle.py -- Crystallized from web AI conversation
# Import with: stato import-bundle stato_bundle.py

SKILLS = {
    "skill_name": '''
class SkillName:
    name = "skill_name"
    version = "1.0.0"
    depends_on = ["packages"]
    @staticmethod
    def run(**kwargs): pass
''',
}

PLAN = '''
class ProjectPlan:
    name = "project_name"
    objective = "what to accomplish"
    steps = [{"id": 1, "action": "step", "status": "pending"}]
'''

MEMORY = '''
class ProjectState:
    phase = "current_phase"
    tasks = ["remaining", "tasks"]
'''

CONTEXT = '''
class ProjectContext:
    project = "project_name"
    description = "what this project is"
'''
```

The parser uses `ast.parse` (no `exec()`) so untrusted bundle files are safe to inspect.

---

## Privacy and Security

Stato includes a privacy scanner that checks for secrets, PII, and sensitive paths before exporting snapshots.

### What gets scanned

The scanner checks for:
- **API keys** : OpenAI, Anthropic, and other common key patterns
- **AWS credentials** : access key IDs and secret keys
- **Database URLs** : connection strings with credentials
- **Home directory paths** : `/home/username/`, `/Users/username/`
- **PII patterns** : patient IDs, email addresses, and other identifiers

### Privacy scan on snapshot

By default, `stato snapshot` runs the privacy scanner before creating an archive:

```bash
stato snapshot --name "export"
# If secrets found: prints findings and exits with error
```

**Options:**

- `--sanitize` : automatically replace detected secrets with placeholders (originals unchanged)
- `--force` : skip the privacy scan entirely

```bash
# Auto-replace secrets in the snapshot (original files untouched)
stato snapshot --name "clean-export" --sanitize

# Skip the scan (you know what you're doing)
stato snapshot --name "internal" --force
```

### .statoignore

Create a `.statoignore` file in your project root to suppress false positives:

```
# .statoignore -- patterns to suppress in privacy scan
# One pattern per line, supports * wildcards
test_api_key_*
example_credentials
```

`stato init` creates a `.statoignore` template automatically.

---

## Advanced

### Comparing modules

Use `stato diff` to compare module versions, snapshots, or individual files.

```bash
stato diff skills/qc.py                        # current vs last backup
stato diff skills/qc_v1.py skills/qc_v2.py     # two module files
stato diff export-v1.stato export-v2.stato      # two snapshot archives
stato diff skills/qc.py --brief                 # show only changed fields
```

### Converting external files

Migrate existing CLAUDE.md, .cursorrules, AGENTS.md, or SKILL.md files into stato modules:

```bash
stato convert CLAUDE.md                  # convert to stato modules
stato convert .cursorrules --dry-run     # preview without writing
```

### Registry

Browse and install shared expertise packages from the community registry:

```bash
stato registry list                          # list all packages
stato registry search "bioinformatics"       # search by keyword
stato registry install scrna-expert          # install a package
```

Packages are community-contributed expertise modules. Each package is privacy-scanned before publishing.

---

## Module Format Reference

### SkillModule

Skills represent executable expertise with learned parameters.

**Required:** `name` (str), `run()` method (callable, `@staticmethod` preferred)

**Optional:** `version` (str, semver), `description` (str), `depends_on` (list), `input_schema` (dict), `output_schema` (dict), `default_params` (dict), `lessons_learned` (str), `tags` (list), `context_requires` (list)

```python
class Normalization:
    """Normalization for scRNA-seq data."""
    name = "normalize"
    version = "1.1.0"
    depends_on = ["scanpy", "qc_filtering"]
    default_params = {"method": "scran"}
    lessons_learned = """
    - scran outperforms log-normalize for heterogeneous tissues
    - For < 200 cells, fall back to simple normalization
    """
    @staticmethod
    def run(adata_path, **kwargs):
        return kwargs
```

### PlanModule

Plans track multi-step workflows with dependency-aware step ordering.

**Required:** `name` (str), `objective` (str), `steps` (list of dicts)

**Step dict fields:** `id` (int, unique), `action` (str), `status` (str: pending|running|complete|failed|blocked)

**Optional step fields:** `depends_on` (list[int]), `params` (dict), `output` (str), `assigned_to` (str), `metrics` (dict), `notes` (str)

**Optional plan fields:** `version` (str), `decision_log` (str), `constraints` (list), `created_by` (str)

```python
class AnalysisPlan:
    name = "cortex_analysis"
    objective = "Complete scRNA-seq analysis pipeline"
    steps = [
        {"id": 1, "action": "load_data", "status": "complete",
         "output": "loaded 15000 cells x 20000 genes"},
        {"id": 2, "action": "qc_filtering", "status": "complete",
         "output": "filtered to 12500 cells using max_pct_mito=20"},
        {"id": 3, "action": "normalize", "status": "complete",
         "output": "scran normalization applied"},
        {"id": 4, "action": "find_hvg", "status": "pending"},
        {"id": 5, "action": "dim_reduction", "status": "pending", "depends_on": [4]},
        {"id": 6, "action": "clustering", "status": "pending", "depends_on": [5]},
        {"id": 7, "action": "marker_genes", "status": "pending", "depends_on": [6]},
    ]
    decision_log = """
    - Chose scran over log-normalize based on benchmark results
    - Will use leiden clustering based on dataset size > 5000 cells
    """
```

**Validation rules:**
- Step IDs must be unique
- `depends_on` must reference existing step IDs (E008)
- The step dependency graph must be acyclic (E009)
- Status must be one of: `pending`, `running`, `complete`, `failed`, `blocked` (E010)
- Missing status is auto-set to `"pending"` (W004)

**Computed properties** (available via `PlanHelpers`):
- `current_step(steps)` : the step with status `"running"`, or None
- `next_step(steps)` : first `"pending"` step whose dependencies are all `"complete"`
- `progress(steps)` : tuple of (completed_count, total_count)
- `is_complete(steps)` : True if all steps are `"complete"`

### MemoryModule

Memory tracks agent working state: what phase it's in, what it's learned, what went wrong.

**Required:** `phase` (str)

**Optional:** `tasks` (list), `known_issues` (dict), `reflection` (str), `error_history` (list), `decisions` (list), `metadata` (dict), `last_updated` (str)

**Convention:** Class name should end with `State` (e.g., `AnalysisState`).

```python
class AnalysisState:
    phase = "analysis"
    tasks = ["find_hvg", "dim_reduction", "clustering", "markers"]
    known_issues = {"batch_effect": "plates 1 and 2 show batch effect"}
    reflection = """
    QC and normalization complete. Data quality is good.
    Batch effect between plates needs correction before clustering.
    """
```

### ContextModule

Context describes the project environment: what datasets exist, what tools to use, what conventions to follow.

**Required:** `project` (str), `description` (str)

**Optional:** `datasets` (list), `environment` (dict), `conventions` (list), `tools` (list), `pending_tasks` (list), `completed_tasks` (list), `team` (list), `notes` (str)

**Convention:** Class name should end with `Context` (e.g., `ProjectContext`).

```python
class ProjectContext:
    project = "cortex_scrna"
    description = "scRNA-seq analysis of mouse cortex P14"
    datasets = ["data/raw/cortex_p14.h5ad"]
    environment = {"scanpy": "1.10.0", "python": "3.11"}
    conventions = [
        "Use scanpy for all analysis",
        "Save figures to figures/ directory",
        "Use .h5ad format for all intermediate files",
    ]
```

---

## Validation Reference

The compiler runs a 7-pass pipeline on every module. Diagnostics are grouped into three tiers.

### Hard Errors (write rejected)

| Code | Condition |
|---|---|
| E001 | Syntax error (`ast.parse` fails) |
| E002 | No class definition found |
| E003 | Missing required field (e.g., `name` for skills, `objective` for plans) |
| E004 | Missing required method (e.g., `run()` for skills) |
| E005 | Runtime execution error (class definition crashes at `exec` time) |
| E006 | Required method not callable |
| E007 | Field type mismatch that can't be auto-corrected (e.g., `depends_on = 42`) |
| E008 | Invalid step dependency, references nonexistent step ID, or duplicate step ID |
| E009 | Circular dependency in plan step DAG |
| E010 | Step status not in allowed set |

### Auto-Corrections (write accepted with warning)

| Code | What it fixes |
|---|---|
| W001 | `depends_on = "scanpy"` -> `depends_on = ["scanpy"]` |
| W002 | `depends_on = 1` -> `depends_on = [1]` |
| W003 | `version = "1.0"` -> `version = "1.0.0"` |
| W004 | Step missing `status` -> adds `status = "pending"` |
| W005 | Multiple classes found -> uses first, warns |
| W006 | Cannot infer module type -> defaults to skill, warns |

### Advice (informational, never blocks)

| Code | Suggestion |
|---|---|
| I001 | Class name doesn't match convention (e.g., memory class should end with `State`) |
| I002 | No docstring on class |
| I003 | No `lessons_learned` on skill |
| I004 | No `decision_log` on plan |
| I006 | `run()` has no type hints |
