# MovieVault v2.0 RC2 — P0 through P2A Remediation Quality Report

This document is part of a **source release candidate**. It is not a certificate that a native Windows installer or provider credentials have been live-tested.

Executed in isolated Linux/Python test environment with synthetic sample media and mocked external API responses:

- `python -m unittest discover -s tests -q` — **94 tests passed in 11.742 seconds**.
- `python -W error::ResourceWarning -m unittest discover -s tests -q` — **94 tests passed in 12.042 seconds** with `ResourceWarning` promoted to an error.
- `python -W error::ResourceWarning -m unittest tests.test_p1a_integrity -v` — dedicated P1A regression tests **7/7 passed in 0.160 seconds**.
- `python -W error::ResourceWarning -m unittest tests.test_p1b_correctness -v` — dedicated P1B regression tests **10/10 passed in 0.194 seconds**.
- `python -m unittest tests.test_p1c_concurrency -v` — dedicated deterministic P1C regression tests **11/11 passed in 0.107 seconds**.
- `python -W error::ResourceWarning -m unittest tests.test_p2a_performance -q` — dedicated P2A correctness, bound, and scale tests **7/7 passed in 5.031 seconds**.
- `python tests/visual_smoke.py` — **PASSED**: synthetic library cards, settings/migration/Gemini controls, subtitle editor, soft-light toggle, Edit-to-Details modal return and Smart Update dialog; Playwright/Chromium with in-memory fake MovieVault API, no real network credentials.
- `python -m compileall -q mv_core.py mv_diagnostics.py mv_gemini.py mv_migration.py mv_playback.py mv_server.py mv_tmdb.py MovieVault.pyw dev.py tests` — **PASSED** Python syntax preparation.
- `ZipFile.testzip` and directory/file security audit on packaged source.
- `python qa_runner.py` — **PASS**: 94 unit/integration tests, Python compilation, and Playwright visual smoke all passed.

P0-specific coverage includes: explicit migration setting allowlisting; unchanged v1 source bytes; sanitization of older pending migrations; one-time cleanup of already migrated catalogs and their backups; pre-activation sanitization of restored v1-derived catalogs through the already-running `Catalog`; corrupt SQLite, missing-table, and missing-required-column rejection before staging; ZIP CRC rejection; corruption after staging; database/poster activation fault injection; rollback of the live catalog; quarantine; privacy-safe recovery logging; and successful reopen after recovery.

P1A-specific coverage includes: replacement of the complete poster generation across overlapping movie IDs; zero-member poster archives; omitted TMDb cache references; preservation of archived manual posters; restoration and private schema normalization of older valid v2 backups; a successful same-instance scan and digest backfill after restoring a database without `content_sha256`; current-version metadata in a same-instance backup after restoring schema 2; validation, staging, and activation of that new backup without restart; disappearance before stat; access loss before fingerprinting; partial-scan continuation and privacy-safe diagnostics; full-digest verification; and the audit's sampled-fingerprint collision reproduction without media modification or incorrect relinking.

P1B-specific coverage includes: deterministic cancellation during title import, ratings import, and ratings download; in-transaction cancellation after title replacement SQL and after ratings replacement/movie refresh SQL but before commit; rollback of live IMDb tables, timestamps, and movie ratings; removal of staging files; completed job state when cancellation arrives after atomic title-index replacement; the audit's locked `tt2222222`/4.2 versus exact-candidate `tt1111111`/9.9 identity case across manual matching, local refresh, scan, TMDb refresh, and ratings import; normal unlocked matching; and a focused year-leading filename corpus.

P1C-specific coverage includes: a manual poster selection racing an in-flight automatic fetch; simultaneous poster writers with complete matching file/database generations and no shared partial file; clear racing background poster work; a manual metadata edit while TMDb refresh is already blocked in progress; simultaneous exclusive job starts with exactly one admission; cancelled-job cleanup followed immediately by an isolated successor; failed-job slot release; backup rejection while a poster commit is inside its unsafe section; root-disable reservation versus scan admission; restore activation reservation versus background-job admission; and reservation release after synchronous activation failure. Race windows use events, barriers, and targeted fault injection.

P2A-specific coverage includes: case-insensitive exact release-group API/backend filtering distinct from free search; YTS/YTSMX/MYTS/YTS-OTHER and QXR/QXR-Group boundaries; blank/literal-Unknown behavior; composition with resolution/year/subtitle filters; one folder snapshot shared by subtitle and local-poster detection; one immutable settings snapshot; bounded valid probe snapshots retaining technical and subtitle fields; compressed, decompressed, row, line, field, and staging-allocation bounds for both IMDb datasets; live-index preservation and stage cleanup on every bound failure; and reproducible 1,000/10,000-movie startup/list/filter/stats/unchanged-scan budgets. See `P2A_REMEDIATION_SUMMARY.md` for exact measurements and limits.

The full suite continues to cover: old v1 preview and import from folder/database/ZIP; manual filename/subtitle preservation; same-row compound subtitle filters; offline/missing; local posters and TMDb mock; playback planner; Gemini suggestion verification; official ratings import; diagnostics redact/rotation; server auth; native WebView recursion regression; browser navigation and Edit-to-Details; backup/restore.

**Not verified here:** build of `.exe` on Windows, user machine WebView2 runtime stability, Windows DPAPI persistence, real external TMDb/Gemini quota/network responses, VLC/mpv installation-specific CLI behavior, or scale benchmarks with thousands of real films. The recorded 1,000/10,000 gates are synthetic Linux measurements only. See `QA_CHECKLIST_AR.md`.

Legacy source and target were generated from test fixtures; no user's actual v1 database was read or uploaded.
