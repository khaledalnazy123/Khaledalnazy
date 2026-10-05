# P1C Concurrency and Operation-Safety Remediation

This batch addresses only the remaining P1 concurrency-safety work from `CODEX_INITIAL_AUDIT.md`. P0, P1A, and P1B protections remain in place; P2, installer, performance, and unrelated UI work are outside this change.

## Poster generation integrity

- Poster images are validated and transcoded into unique private temporary files. No two writers share a `.partial` path, and only a complete JPEG is published with atomic `os.replace`.
- A short catalog-wide poster-generation guard coordinates each file/database commit with backup and restore. Per-movie locks allow unrelated movies to proceed concurrently.
- Each movie has an in-process poster generation token. TMDb, Commons, local-file, and frame work captures the token before slow work and must still own that generation before publishing.
- A later manual upload, lock change, or clear invalidates older in-flight work. Manual/newer user intent therefore wins without leaving mismatched database metadata and bytes.
- Poster-provider configuration has its own generation token, so disconnecting or changing providers also invalidates older provider work and its stale attempt bookkeeping.
- Poster commit failures restore the previous managed file (or remove the newly published file when no previous file existed) while SQLite rolls back its metadata update.
- Expiration rechecks that the current poster is still TMDb artwork under the same coordination before clearing it.

## Synchronous mutations versus background jobs

- Manual movie metadata updates and provider/scan metadata commits use a narrow per-movie lock.
- Scan, local IMDb refresh, post-import enrichment, TMDb refresh, and verified AI commits re-read the current row and `manual_fields` after acquiring that lock. A stale background snapshot cannot overwrite a newer manual edit.
- Subtitle edits and scan subtitle reconciliation share the owning movie lock.
- Disabling a root while a library job owns a scan/update snapshot returns `BusyError`; adding/enabling a root remains available because it affects later snapshots.
- Backup uses a SQLite snapshot for both catalog and poster-source selection, and holds the poster-generation guard while copying poster members. If a poster is inside its short unsafe commit section, backup returns `BusyError` instead of producing a mixed generation.
- Restore staging remains a private validated copy. Live restore activation requires the job slot to be idle and holds the poster-generation guard through database/poster generation replacement and rollback.

## Job lifecycle safety

- Exclusive job admission remains atomic under `job_lock`; simultaneous attempts admit exactly one operation.
- Unsafe synchronous maintenance claims a small reservation under that same `job_lock`. Claiming atomically verifies that no job is active, and `start_job()` rejects admission until the reservation is released.
- Root disabling holds the reservation through its root/movie status transaction. Restore activation holds it through the complete database/poster replacement or rollback boundary.
- The reservation is context-managed and always releases in `finally`, including validation, database, activation, and rollback failures.
- Completion, cancellation-state resolution, and release of the active slot are published together under the same lock.
- A finishing worker clears `active_job` only when it still owns that exact job ID, so it cannot erase a newer job's active marker.
- Cancellation is stored on the targeted job only. Failed and cancelled jobs release the slot, and an immediate successor starts with independent state.

## Mutation audit and classification

| Mutation surface | Execution | Previous risk | P1C classification / coordination |
|---|---|---|---|
| Movie metadata (`patch_movie`, manual IMDb match) | Synchronous API | Could overlap stale scan/provider snapshots | Safe: per-movie lock; background commits re-read current manual locks |
| Scan and smart-update movie fields | Background exclusive job | Could commit metadata derived before a manual edit | Safe: per-movie commit lock and current-row re-read |
| Subtitle metadata and scan reconciliation | Synchronous API / background scan | Edit and reconciliation could update the same rows | Safe: shared owning-movie lock |
| Manual poster upload / lock / clear | Synchronous action | Could be overwritten by older automatic work | Safe: poster generation invalidation; newest user action wins |
| Local, TMDb, Commons, batch, and frame posters | Background job or scan helper | Shared partial path and stale publication | Safe: unique temp, generation check, per-movie commit lock, atomic replace |
| Poster expiration | Startup maintenance | Could clear a newer poster selected after its query | Safe: source recheck and coordinated clear |
| Root add/enable | Synchronous API | New root is outside an existing scan snapshot | Safe without blocking; visible to the next scan |
| Root disable | Synchronous API | Could race scan admission after an idle check | Exclusive reservation covers the full root/movie status transaction |
| Settings and provider connect/disconnect | Synchronous API | Background work may already hold a validated client/settings snapshot | Safe: changes affect subsequent work; commits remain transactional and secret stores stay separate |
| IMDb title/rating imports | Background exclusive job | Live replacement/cancellation races | Safe: existing P1B transactional replacement and pre-commit cancellation retained |
| Backup | Synchronous API | Database snapshot and poster bytes could come from different generations | Safe snapshot plus poster guard; `BusyError` during unsafe poster commit |
| Restore/migration staging | Synchronous private staging | Does not mutate the active catalog | Safe and independently validated before activation |
| Restore activation | Startup/live generation replacement | Could admit a job after an idle check but before replacement | Exclusive reservation plus poster guard covers activation and rollback |
| Job start/cancel/finalize | API/background worker | Stale cleanup or sync-maintenance TOCTOU could corrupt ownership | Safe: ID-scoped cancellation, reservation-aware admission, and atomic locked lifecycle transitions |

This deliberately avoids a global block on ordinary reads, settings, provider configuration, movie edits for unrelated IDs, or long network/image preparation. Coordination covers only admission, the affected movie, or the short poster commit/backup generation boundary.

## Verification

- Dedicated deterministic P1C regression tests: **11/11 passed in 0.107 seconds**.
- Full unit/integration suite: **87/87 passed in 6.662 seconds**.
- Strict full suite: **87/87 passed in 6.653 seconds** with `ResourceWarning` promoted to an error.
- Python compilation: **PASSED**.
- Automated QA runner: **PASS** for 87 unit/integration tests, Python compilation, and Playwright visual smoke.
- Standalone Playwright visual smoke: **PASSED** with three movie cards, settings panels, two subtitle rows, modal navigation, and no page errors.

The concurrency tests use `threading.Event` and `threading.Barrier` synchronization plus targeted fault injection; arbitrary delays are not used to create the tested race windows. No Windows, WebView2, DPAPI, packaged executable, installer, VLC/mpv, or live-provider verification was performed in this batch.
