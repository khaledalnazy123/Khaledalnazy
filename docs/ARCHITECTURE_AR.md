# MovieVault v2 — architecture overview

- **Desktop entry:** `MovieVault.pyw` → `mv_server.run_app`; browser diagnostic alternative via `dev.py --browser`.
- **Localhost API:** `mv_server.py`, bound to `127.0.0.1` and protected by per-run random token; static page `web/index.html`, logic `web/app.js`, theme `web/style.css`.
- **Catalog and scan:** `mv_core.Catalog` on SQLite with additive schema migrations, file fingerprints and FFprobe; original filename remains immutable.
- **Migration:** `mv_migration.py`, source read-only, preview counts, SQLite snapshot to v2/migration_pending and atomic activation on next start. v2 stores data separately from legacy v1.
- **Playback:** `mv_playback.py`; no renaming of user file; optional selection through VLC/mpv.
- **Online sources:** `mv_tmdb.py` official movie/poster metadata; `mv_gemini.py` opt-in spelling assistance with independently verified IDs; official IMDb textual data and ratings imported by `mv_core.py`.
- **Diagnostics:** `mv_diagnostics.py`, local rotating log + explicit privacy-minimized ZIP export.
- **Installer:** `build_windows.ps1`, `BUILD_WINDOWS.cmd`, `MovieVault.iss`; v2 has a distinct Inno AppId and installation destination from v1.
- **Automated QA:** `tests/` unit/integration/regression; `tests/visual_smoke.py` optionally uses Playwright and a synthetic API fixture; no real user data or credentials.

V2 data: `%LOCALAPPDATA%\MovieVault\v2`. Legacy v1 data: `%LOCALAPPDATA%\MovieVault`. Actual movies stay in their existing folder paths.
