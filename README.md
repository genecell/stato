# Stato

**The Expertise Layer for AI Agents**

Capture, validate, and transfer AI agent expertise.

[![PyPI](https://img.shields.io/pypi/v/stato)](https://pypi.org/project/stato/)
[![Tests](https://img.shields.io/badge/tests-353%20passing-green)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## What Is Stato?

**Think: npm for agent expertise, with a built-in compiler.**

Stato combines what pip does (install, share, registry) with what a compiler does (validate, reject invalid input) for a new kind of artifact: agent knowledge instead of code.

| If you know... | Stato is like... |
|---|---|
| npm / pip | Install, share, and version expertise packages |
| TypeScript / GCC | 7-pass compiler validates before anything hits disk |
| Docker | Package expertise so it works on any platform |
| Git | Snapshot, diff, and merge expertise |

What no existing tool does: the agent extracts its own knowledge (crystallization), privacy scanning before export, and a composition algebra for expertise modules.

> **Compaction is your agent's working memory. Stato is its long-term memory —
> validated, on disk, portable.** Where Mem0/Zep/Letta are services and skills
> marketplaces distribute single skills, stato distributes *whole validated
> cognitive-state archives* (context + plan + memory + skills) that any tool
> and any teammate can load.

### Three ways stato integrates with your agent

A tool needs only one tier to work with stato; each higher tier deepens it.

| Tier | What it does | How |
|---|---|---|
| **Instructions** | Static index any tool reads | `stato bridge` → AGENTS.md, CLAUDE.md, `.cursor/rules/*.mdc`, copilot, GEMINI.md, SKILL.md |
| **Hooks** | Auto-restore state after compaction | `stato hooks install` → Claude Code, Codex CLI, Gemini CLI |
| **MCP** | Live state + validate-gated writes | `stato mcp` → every MCP client at once |

### Quickstart per agent

One command wires stato into your agent (it then reads the generated guidance
automatically):

| Agent | One command |
|---|---|
| **Claude Code** | `pip install stato && stato bridge --platform claude` |
| **Codex CLI** | `pip install stato && stato bridge --platform agents` |
| **Cursor** | `pip install stato && stato bridge --platform cursor` |
| **Gemini CLI** | `pip install stato && stato bridge --platform gemini` |
| **GitHub Copilot** | `pip install stato && stato bridge --platform copilot` |
| **Any MCP client** | `pip install "stato[mcp]" && stato init --mcp` then run `stato mcp` |

Deeper integration (optional): `stato skill install --tool <agent>` ships the
"how to use stato" skill, and `stato init --mcp` exposes live tools like
`stato_workspace(task)`.

**Starting from scratch** (no `.stato/` yet): `pip install stato && stato init
&& stato crystallize`, then tell your agent to *"read and follow
`.stato/prompts/crystallize.md`"*, then `stato validate .stato/` and
`stato bridge --platform <agent>`.

![Stato Overview](docs/figures/stato_figures.png)

## Install

    pip install stato

Install from GitHub (latest development version):

    pip install git+https://github.com/genecell/stato.git

## Quick Start

### Across Sessions (Same Project)

Your agent forgets between sessions. Stato makes its knowledge persist on disk.

    # Session 1: agent captures expertise
    cd my-project
    stato init
    stato crystallize
    # Saves prompt to .stato/prompts/crystallize.md

    # Ask your coding agent to capture its expertise:
    #   "Read and follow .stato/prompts/crystallize.md"
    # Agent writes .stato/ modules based on what it learned.

    # Verify and generate bridge
    stato validate .stato/
    stato bridge --platform claude

    # Session 2 (next day, after /compact, new terminal):
    # CLAUDE.md and .stato/ files are still on disk.
    # Agent reads CLAUDE.md automatically.
    stato resume             # structured recap if needed

No export. No import. Files on disk persist across every session.

### Across Projects and People

Transfer expertise to a new project, a teammate, or the community.

    # Export
    stato snapshot --name scrna-expert --sanitize

    # Import into new project
    cd ~/new-project && stato init
    stato import scrna-expert.stato

    # Or install from the community registry
    stato registry install piaso-scrna-skills-testing

**Composition algebra** for working with expertise archives:

| Operation | Command | What it does |
|---|---|---|
| Snapshot | `stato snapshot` | Bundle all expertise into a portable archive |
| Slice | `stato slice --module skills/qc` | Extract specific skills with dependencies |
| Graft | `stato graft external-skill.py` | Add one external skill with validation |
| Merge | `stato merge a.stato b.stato` | Combine expertise from multiple sources |

### Across Platforms

Same expertise, different coding agents. One command generates every bridge:

    stato bridge --platform all

    # Creates the file each tool reads automatically:
    #   AGENTS.md                           -> Codex, and most agents (cross-tool standard)
    #   CLAUDE.md                           -> Claude Code
    #   .cursor/rules/stato.mdc             -> Cursor
    #   .github/copilot-instructions.md     -> GitHub Copilot
    #   GEMINI.md                           -> Gemini CLI
    #   README.stato.md                     -> anything else / humans

### From Web AI to Coding Agent

Plan architecture in Claude.ai or ChatGPT. Build in any coding agent.

    stato crystallize --web
    # Paste prompt into web AI -> get bundle -> save as stato_bundle.py
    stato import-bundle stato_bundle.py
    stato bridge --platform cursor

## Why Stato Exists

AI coding agents are powerful but stateless. Every session starts from zero. Expertise earned in one session, one project, or one platform stays trapped there.

Stato treats agent expertise like code: captured in structured modules, validated by a 7-pass compiler, composed with algebraic operations, and portable across any platform. Your agent's knowledge becomes a permanent, shareable, validated artifact.

[Read the full story ->](https://stato.hiniki.com)

## Features

| Feature | Description |
|---|---|
| Crystallize | Agent captures its own knowledge into structured modules |
| 7-Pass Compiler | Validates syntax, structure, types, schema, semantics before writing |
| Composition Algebra | Snapshot, slice, graft, merge expertise archives |
| Cross-Platform Bridges | AGENTS.md, CLAUDE.md, .cursor/rules/*.mdc, Copilot, GEMINI.md, SKILL.md from one source |
| Workspace | Assemble only the skills relevant to the current task (progressive disclosure) |
| Audit | Score module quality 0–10 with concrete gaps; gate publishing |
| Reflect | Surface dead-ends (reverted values) from edit history as candidate lessons |
| Team Assembly | Generate expertise-scoped subagents from a team spec |
| MCP Server | Expose live state + validate-gated write tools to any MCP client |
| Hooks | Auto-restore state after compaction (Claude Code, Codex, Gemini) |
| Web AI Bridge | Import expertise from Claude.ai, ChatGPT, Gemini conversations |
| Privacy Scanner | 19 patterns detect secrets, emails, paths before export |
| Resume | Restore full context after /compact or session restart |
| Convert | Migrate existing CLAUDE.md, .cursorrules, SKILL.md into stato |
| Registry | Search and install community expertise packages |
| Diff | Field-level comparison between module versions |

## CLI Reference

**State**

| Command | Description |
|---|---|
| `stato init` | Initialize a stato project (`--mcp` also writes `.mcp.json`) |
| `stato validate` | Run 7-pass compiler on modules (`--strict`, `--error-code`) |
| `stato audit` | Score module quality 0–10 with gaps (`--min` to gate) |
| `stato status` | Show all modules, plan progress, warnings |
| `stato resume` | Generate context recap for session restoration |
| `stato workspace [TASK]` | Assemble the skills relevant to the current task |
| `stato reflect` | Surface reverted/churned values from history as candidate lessons |
| `stato crystallize` | Save the capture prompt (`--print`, `--web`) |
| `stato find` | Search local skills by name, tags, and lessons |
| `stato config` | Show effective config and its sources (`--init`) |
| `stato doctor` | Report binary path, version, project state, hooks, MCP |
| `stato migrate-lessons` | Convert prose lessons into structured entries |

**Composition & sharing**

| Command | Description |
|---|---|
| `stato snapshot` | Export expertise as a checksummed portable archive |
| `stato import` | Import modules from a .stato archive (verified) |
| `stato import-bundle` | Import from a web AI bundle file |
| `stato inspect` | Preview archive contents + integrity |
| `stato slice` | Extract specific modules with dependencies |
| `stato graft` | Add external module with validation |
| `stato merge` | Combine two archives with conflict resolution |
| `stato diff` | Compare module versions / archives |
| `stato convert` | Migrate from CLAUDE.md, .cursorrules, SKILL.md, etc. |
| `stato registry search/install/list/package` | Search, install, and package community expertise |

**Bridges, hooks, MCP, teams, skill**

| Command | Description |
|---|---|
| `stato bridge --platform <agent>` | Generate the instruction file each tool reads |
| `stato hooks install` | Auto-restore state after compaction (`--reminders`) |
| `stato mcp` | Run the MCP server (resources + validate-gated tools) |
| `stato team assemble` | Generate expertise-scoped subagents from `.stato/team.toml` |
| `stato skill install` | Install the "how to use stato" Agent Skill into a tool |

Full documentation: [stato.hiniki.com](https://stato.hiniki.com/getting-started/installation/) | [USAGE.md](USAGE.md)

## Comparison

Against the neighbouring categories — static instruction files, agent-memory
services, and skills marketplaces. Stato's lane is a **validated, portable,
tool-agnostic memory + evaluation layer**; where another category genuinely does
something, the table says so.

| Capability | Stato | Instruction files (CLAUDE.md / AGENTS.md / .cursor rules) | Agent memory (Mem0 / Letta) | Skills marketplaces (Agent Skills) |
|---|---|---|---|---|
| Validated before it persists | 7-pass compiler | none | none | none |
| Imported expertise can't execute code | AST-only, no `exec` | n/a (text) | n/a | skills may run code |
| One source → many tools | 6 bridges + MCP + hooks | one format per tool | SDK/service-tied | portable skill files |
| Portable, checksummed archives | `.stato` + sha256 | manual copy | service-hosted | folder copy |
| Task-scoped context (not the whole dump) | workspace + summaries | static, whole file | retrieval | static |
| Recovers state after compaction | hooks (Claude/Codex/Gemini) | no | varies | no |
| Live, validate-gated writes | MCP tools | no | writes (unvalidated) | no |
| Learns from failures (edit history) | `stato reflect` | no | no | no |
| Composition algebra | snapshot/slice/graft/merge | manual copy | no | no |
| Privacy scan before sharing | 19 patterns | none | none | none |
| Agent self-capture | crystallize | human-authored | auto (opaque) | human-authored |
| Human-readable & git-native | typed Python modules | markdown | opaque store | markdown |

Stato composes with these rather than replacing them — it *generates* the
instruction files, exposes an MCP server, and can export Agent Skills.

## Registry

Browse and install shared expertise packages:

    stato registry list
    stato registry search "scrna"
    stato registry install piaso-scrna-skills-testing

## Contributing

https://github.com/genecell/stato

Issues and PRs welcome.

## Contact

Min Dai - dai@broadinstitute.org

[Fishell Laboratory](https://fishelllab.hms.harvard.edu/), Harvard Medical School and the Broad Institute of MIT and Harvard.

## License

MIT
