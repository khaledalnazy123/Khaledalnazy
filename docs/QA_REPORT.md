# MovieVault v2.0 RC2 — Automated Quality Report

This document is part of a **source release candidate**. It is not a certificate that a native Windows installer or provider credentials have been live-tested.

Executed in isolated Linux/Python test environment with synthetic sample media and mocked external API responses:

- `python -m unittest discover -s tests -q` — **50 tests passed** (approx. 7 seconds). Some tests emitted ResourceWarnings from synthetic SQLite fixtures; no test assertion failed.
- `python tests/visual_smoke.py` — **PASSED**: synthetic library cards, settings/migration/Gemini controls, subtitle editor, soft-light toggle, Edit-to-Details modal return and Smart Update dialog; Playwright/Chromium with in-memory fake MovieVault API, no real network credentials.
- `python -m compileall -q mv_*.py MovieVault.pyw dev.py tests` — **PASSED** Python syntax preparation.
- `ZipFile.testzip` and directory/file security audit on packaged source.

Coverage includes: old v1 preview and import from folder/database/ZIP; unchanged legacy data and staging guard; manual filename/subtitle preservation; same-row compound subtitle filters; offline/missing; local posters and TMDb mock; playback planner; Gemini suggestion verification; official ratings import; diagnostics redact/rotation; server auth; native WebView recursion regression; browser navigation and Edit-to-Details; backup/restore.

**Not verified here:** build of `.exe` on Windows, user machine WebView2 runtime stability, Windows DPAPI persistence, real external TMDb/Gemini quota/network responses, VLC/mpv installation-specific CLI behavior, scale benchmarks with thousands of real films. See `QA_CHECKLIST_AR.md`.

Legacy source and target were generated from test fixtures; no user's actual v1 database was read or uploaded.
