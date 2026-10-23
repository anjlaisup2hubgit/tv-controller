# Changelog

Log every feature **Added** and **Removed**. Newest first.

## 2026-10-23
### Added
- Multi-brand drivers (Android TV, Roku, Samsung, LG webOS), web server and remote UI (`8183a4f`)
- Android TV discovery and remote sample (`0d5ee79`)
- Project docs: README, CLAUDE.md, docs/, docs/components/

### Removed
- Nothing yet

### Changed
- Moved Python modules into `src/`; run with `python src/server.py`. `web/`, `cert.pem`, `key.pem`, `settings.json` stay in the project root.

- Moved `cert.pem`/`key.pem` to `certs/`, `settings.json` to `data/` (both git-ignored), component notes to `docs/components/`, and pointed the server at `public/` (was `web/`).
