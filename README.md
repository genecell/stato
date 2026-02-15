# Stato

**The Expertise Layer for AI Agents**

Capture, validate, and transfer AI agent expertise.

[![PyPI](https://img.shields.io/pypi/v/stato)](https://pypi.org/project/stato/)
[![Tests](https://img.shields.io/badge/tests-130%2B%20passing-green)]()
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

## Install

    pip install stato

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
    stato registry install genecell/scrna-expert

**Composition algebra** for working with expertise archives:

| Operation | Command | What it does |
|---|---|---|
| Snapshot | `stato snapshot` | Bundle all expertise into a portable archive |
| Slice | `stato slice --module skills/qc` | Extract specific skills with dependencies |
| Graft | `stato graft external-skill.py` | Add one external skill with validation |
| Merge | `stato merge a.stato b.stato` | Combine expertise from multiple sources |

### Across Platforms

Same expertise, different coding agents. One command.

    stato bridge --platform all

    # Creates:
    #   CLAUDE.md      -> Claude Code reads automatically
    #   .cursorrules   -> Cursor reads automatically
    #   AGENTS.md      -> Codex reads automatically

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
| Cross-Platform Bridges | CLAUDE.md, .cursorrules, AGENTS.md from one source |
| Web AI Bridge | Import expertise from Claude.ai, ChatGPT, Gemini conversations |
| Privacy Scanner | 19 patterns detect secrets, emails, paths before export |
| Resume | Restore full context after /compact or session restart |
| Convert | Migrate existing CLAUDE.md, .cursorrules, SKILL.md into stato |
| Registry | Search and install community expertise packages |
| Diff | Field-level comparison between module versions |

## CLI Reference

| Command | Description |
|---|---|
| `stato init` | Initialize a stato project |
| `stato crystallize` | Save prompt for agent to capture expertise |
| `stato crystallize --print` | Print full crystallize prompt to terminal |
| `stato crystallize --web` | Generate prompt optimized for web AI |
| `stato validate` | Run 7-pass compiler on modules |
| `stato status` | Show all modules, plan progress, warnings |
| `stato bridge` | Generate platform bridge files |
| `stato resume` | Generate context recap for session restoration |
| `stato diff` | Compare module versions |
| `stato snapshot` | Export expertise as portable archive |
| `stato import` | Import modules from .stato archive |
| `stato import-bundle` | Import from web AI bundle file |
| `stato inspect` | Preview archive contents |
| `stato slice` | Extract specific modules with dependencies |
| `stato graft` | Add external module with validation |
| `stato merge` | Combine two archives with conflict resolution |
| `stato convert` | Migrate from CLAUDE.md, .cursorrules, SKILL.md |
| `stato registry list` | List available packages |
| `stato registry search` | Search packages by keyword |
| `stato registry install` | Install a community package |

Full documentation: [stato.hiniki.com/docs](https://stato.hiniki.com/getting-started/installation/)

## Comparison

| Capability | Stato | Plain CLAUDE.md | SkillKit | MemGPT | CrewAI |
|---|---|---|---|---|---|
| Validated modules | 7-pass compiler | No validation | No validation | No | No |
| Cross-platform | 4 platforms | Claude only | Claude only | OpenAI only | Framework-locked |
| Composition algebra | snapshot, slice, graft, merge | Manual copy | No | No | No |
| Privacy scanning | 19 patterns | None | None | None | None |
| Web AI bridge | Import from any chat | No | No | No | No |
| Agent self-capture | Crystallize prompt | Human-authored | Human-authored | Auto (opaque) | Config files |
| Package registry | GitHub-based | No | No | No | No |
| Session resume | Structured recap | Re-read file | No | Built-in | No |

## Registry

Browse and install shared expertise packages:

    stato registry list
    stato registry search "bioinformatics"
    stato registry install scrna-expert

## Contributing

    git clone https://github.com/genecell/stato.git
    cd stato
    pip install -e ".[dev]"
    pytest tests/ -m "not agent" -v

Run `stato resume` in the repo to understand the project architecture.

Full architecture documentation: [stato.hiniki.com/reference/architecture/](https://stato.hiniki.com/reference/architecture/)

## Acknowledgments

Built at the [Fishell Lab](https://fishelllab.hms.harvard.edu/), Harvard Medical School and the Broad Institute of MIT and Harvard.

## License

MIT
