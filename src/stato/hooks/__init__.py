"""Stato hooks — Design A compaction integration for Claude Code, Codex, Gemini.

Two hook-side behaviors, exposed as hidden CLI commands that read the host's
hook JSON on stdin:

- pre-compact: injects summary-shaping instructions into the compaction
  summarizer (and, when the freshness gate is on, blocks auto-compaction when
  the on-disk state is stale).
- session-start: injects `stato resume --brief` so validated ground truth
  re-enters context after compaction and on new/resumed sessions.

The installers write these into each platform's native hook config,
merge-not-overwrite.
"""
