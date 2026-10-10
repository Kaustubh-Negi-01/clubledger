# Folder reorganization and verification

This change reorganizes the approved ClubLedger application into clearly separated frontend, backend, configuration and database folders. It was verified locally before publication to `master` at the project owner's request.

## What moved

| Earlier location | Current location |
| --- | --- |
| `clubledger/` Python source | `backend/clubledger/` |
| `clubledger/<feature>/routes.py` | `backend/clubledger/api/<feature>.py` |
| `clubledger/web/routes.py` | `backend/clubledger/api/workspace.py` |
| `clubledger/web/ui.py`, `qr.py` | `backend/clubledger/presentation/` |
| `clubledger/web/templates/` | `frontend/templates/` |
| `clubledger/web/static/` | `frontend/static/` |
| `clubledger/migrations/` | `database/migrations/` |
| Previous preview SQLite file | `database/runtime/clubledger-preview.db` |
| `data/.sim_secret`, receipt storage | Private files under `database/runtime/` |

Package installation, imports, template lookup, static asset lookup, migration lookup and test imports were updated. `clubledger` remains the Python package name, so commands still use `python -m clubledger.cli`.

## Readability changes

- Python was formatted into indented, multiline blocks.
- Application JavaScript and CSS were expanded into readable files.
- 55 inline style attributes were extracted into `frontend/static/page-layouts.css`.
- HTML event handlers were replaced by external JavaScript and data attributes.
- Confetti placement uses declared CSS classes instead of JavaScript-generated inline styles.
- Templates have separated HTML structure and Jinja statements with short explanatory comments.
- Module explanations and key function docstrings were added. Existing detailed service comments were retained.
- Navigation labels and permission-linked menu items live in `presentation/navigation.py` rather than long lists embedded in HTML.
- Third-party HTMX source is readable and separated in `static/vendor/`; it remains unused by the current page layout.

Normal template values such as `{{ payment.amount_paise }}` remain in HTML: these are data placeholders, not inline CSS or browser JavaScript.

## Documentation

Read `START_HERE.md`, then `FILE_GUIDE.md`. `API_REFERENCE.md` lists source-derived HTTP endpoints. `DATABASE_STRUCTURE.md` describes the schema. `REVIEWER_PREPARATION.md` walks through a purchase and provides questions the team should be able to answer.

The original contract and build-order documents remain as historical planning references; their old paths map to the locations above. Their rules and migration contents were not rewritten.

## Verified results

- **222 tests passed**, with one existing Starlette/HTTPx deprecation warning.
- Configured Ruff checks passed; browser JavaScript syntax checked with `node --check`.
- New regression checks serve moved CSS, JavaScript, font and illustration resources.
- New regression checks inspect 20 rendered navigation pages for inline styles, embedded scripts and HTML event handlers.
- The preview database's business records match the backup across all **35 tables**. Session identity fields were also preserved; last-seen timestamps may change when browsing.
- All ten migration files retain their original SHA-256 checksums. Running migrate on the preview reports no pending migrations; financial integrity checks pass.
- A wheel package builds and contains the frontend assets and all ten migrations, with no runtime databases or local secrets.
- Local `.env`, preview database and generated simulator secret are ignored by Git.
- Preview server runs at `http://127.0.0.1:8010/dashboard`. Dashboard, navigation and payment feedback are checked in the browser after the moves.

Three initially failing assertions after HTML formatting checked literal source whitespace. They were changed to verify visible heading, size and table-cell content. Pricing remained server-calculated; backend rules were not relaxed.

Requirement evidence remains **20/110** marked implemented, 90 planned; progress mode passes. Test count is not an external evaluator score.

## Local recovery copy

Before moving files, source, tests, docs and the preview database were backed up under the workspace's `work/before-folder-reorganization/`. That backup is outside the repository. The previous preview file was also retained. Use the running database under `database/runtime/` for continued testing.
