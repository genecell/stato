# Contributing a package to the stato registry

The registry indexes shareable `.stato` expertise archives. The best packages
are **crystallized from real work**, not hand-written — that's where the value
is (the WHY behind parameters and decisions).

## Publish flow

1. **Capture** expertise in a project's `.stato/` (crystallize during real runs).
2. **Audit** it — packages should clear a quality bar:
   ```bash
   stato audit .stato/ --min 7
   ```
3. **Snapshot** the shareable modules (skills + context; runtime plan/memory
   are usually excluded or `--template`-reset):
   ```bash
   stato snapshot --name my-package --type skill --type context \
     --output docs/registry/packages/my-package.stato
   ```
   This produces a format-v1 archive with per-module sha256 checksums.
4. **Generate the index entry** (computes the archive's sha256):
   ```bash
   stato registry package docs/registry/packages/my-package.stato \
     --url https://github.com/genecell/stato/raw/master/docs/registry/packages/my-package.stato \
     --author you
   ```
5. **Add** the printed `[packages.<name>]` block to `docs/registry/index.toml`
   and open a PR with both the `.stato` file and the index entry.

## Quality conventions

- **One concern per skill.** Prefer ~5–15 focused lessons per skill over a
  single mega-file; small, scoped skills compose and subagent-scope far better.
- **Provenance.** Set `source` and `confidence` on skills. If a package is a
  starter/template rather than crystallized experience, say so in `source` and
  set `confidence` low (e.g. 0.4) so consumers calibrate trust.
- **Validate & audit.** Every package must pass `stato validate` and should
  audit ≥ 7/10. Fix the gaps `stato audit` reports before submitting.
- **Checksums.** Never hand-edit a `.stato` after computing its index sha256 —
  re-run `stato registry package` if you change it, or `stato import` will
  reject it as tampered.

## Notes on the current packages

- `stato-self` — stato's own development expertise.
- `piaso-scrna-skills-testing` — real scRNA-seq analysis skills from PIASO runs.
- `piaso-infog-normalization`, `piaso-dimreduction`, `piaso-markers-plus` —
  domain-focused repackagings of the above; `piaso-markers-plus` includes one
  **scaffold** skill (`piasomarkerdb_celltyping`, `confidence = 0.4`) that
  should be replaced with a crystallized version from a real PIASOmarkerDB run.
