# MovieVault v2.0 RC2 — P0 Remediation Quality Report

This document is part of a **source release candidate**. It is not a certificate that a native Windows installer or provider credentials have been live-tested.

Executed in isolated Linux/Python test environment with synthetic sample media and mocked external API responses:

- `python -m unittest discover -s tests -q` — **57 tests passed in 6.192 seconds**. A stricter standalone run with `ResourceWarning` promoted to an error also passed all 57 tests.
- `python tests/visual_smoke.py` — **PASSED**: synthetic library cards, settings/migration/Gemini controls, subtitle editor, soft-light toggle, Edit-to-Details modal return and Smart Update dialog; Playwright/Chromium with in-memory fake MovieVault API, no real network credentials.
- `python -m compileall -q mv_*.py MovieVault.pyw dev.py tests` — **PASSED** Python syntax preparation.
- `ZipFile.testzip` and directory/file security audit on packaged source.
- Timestamped machine-readable results: `qa_reports/QA_20261005_094324.json` and `qa_reports/QA_20261005_094324.txt`.

P0-specific coverage includes: explicit migration setting allowlisting; unchanged v1 source bytes; sanitization of older pending migrations; one-time cleanup of already migrated catalogs and their backups; corrupt SQLite and missing-table rejection before staging; ZIP CRC rejection; corruption after staging; database/poster activation fault injection; rollback of the live catalog; quarantine; privacy-safe recovery logging; and successful reopen after recovery.

The full suite continues to cover: old v1 preview and import from folder/database/ZIP; manual filename/subtitle preservation; same-row compound subtitle filters; offline/missing; local posters and TMDb mock; playback planner; Gemini suggestion verification; official ratings import; diagnostics redact/rotation; server auth; native WebView recursion regression; browser navigation and Edit-to-Details; backup/restore.

**Not verified here:** build of `.exe` on Windows, user machine WebView2 runtime stability, Windows DPAPI persistence, real external TMDb/Gemini quota/network responses, VLC/mpv installation-specific CLI behavior, scale benchmarks with thousands of real films. See `QA_CHECKLIST_AR.md`.

Legacy source and target were generated from test fixtures; no user's actual v1 database was read or uploaded.
