# MovieVault v2.0 Independent Engineering Audit

**Audit date:** 2026-10-05 (Africa/Cairo)  
**Audited commit:** `f042331eb4675fca19666607ff3493594e72525c` (`origin/main`)  
**Audit platform:** Linux 6.18, Python 3.12.14, SQLite, FFmpeg/FFprobe, Chromium/Playwright  
**Windows execution:** Not performed. No Windows, WebView2, DPAPI, Inno Setup, packaged EXE, VLC, or mpv result in this report is presented as passed.

## Executive assessment

MovieVault has a sensible local-first shape: a loopback-only HTTP service, a compact browser/WebView frontend, SQLite persistence, isolated provider clients, staged migration/restore, and argument-list subprocess execution. The source implements most of the controls shown in the UI. The strongest areas are original-filename preservation, conservative exact provider matching, same-row subtitle filtering, local-only scanning, explicit external-subtitle playback plans, and the separation of provider credentials from the current v2 SQLite database.

The current repository is **not release-ready**. Two findings are release blockers:

1. v1 migration copies arbitrary legacy `settings` rows, including secret-bearing rows, even though the UI and migration manifest promise that credentials are not imported.
2. restore staging accepts an archive whose database is corrupt; the next launch fails before the UI opens, retains the pending archive, and repeats the failure on later launches.

These are the only two confirmed defects designated as release-blocking: **MV-AUD-001** and **MV-AUD-002**. MV-AUD-003 through MV-AUD-008 are reproducible Medium-severity correctness and reliability defects. MV-AUD-009 through MV-AUD-012 remain confirmed supplementary UI/build findings and are not part of the eight runtime-defect set.

Restore can also attach a stale poster from the pre-restore catalog to a different restored movie when the backup intentionally excludes TMDb cache files. Other confirmed defects affect scan resilience, job cancellation, IMDb identity consistency, movie titles beginning with a year, release-group collections, content relinking, build exit status, and release-version consistency.

The 50 existing tests are useful regression tests, but they primarily exercise happy paths and mocked providers. They do not establish compatibility with a real v1 database, recovery after interrupted activation, native Windows behavior, provider contracts, large-library performance, or installer correctness.

## 1. Architecture assessment

### Runtime architecture

- `MovieVault.pyw` starts `mv_server.run_app`; `dev.py` provides browser-mode diagnostics.
- `mv_server.py` binds `ThreadingHTTPServer` to `127.0.0.1` and protects API calls with a per-process random token plus Host and Origin validation.
- `web/index.html`, `web/app.js`, and `web/style.css` implement the UI. Dynamic catalog values are consistently passed through `esc()` before insertion into HTML.
- `mv_core.Catalog` owns schema creation, settings, scanning, filtering, metadata, jobs, posters, IMDb import, backup, and restore. At 1,113 lines it is the main architectural concentration of risk.
- `mv_migration.py` implements copy-only v1 preview, staging, and activation.
- `mv_tmdb.py` and `mv_gemini.py` constrain endpoints, response sizes, redirects, and credential persistence. Credentials are DPAPI-protected on Windows and memory-only on non-Windows development systems.
- `mv_playback.py` constructs argument lists for mpv/VLC without shell execution and validates external subtitle membership and location.
- `mv_diagnostics.py` writes bounded structured logs and exports a ZIP without the live database or credential files.
- The Windows release path is PowerShell + PyInstaller + Inno Setup, with a separate v2 AppId and install directory.

### Data architecture

SQLite uses per-operation connections, WAL mode, foreign keys, a 45-second busy timeout, and additive schema updates. Core records are `roots`, `movies`, `subtitles`, `settings`, `imdb_titles`, and `imdb_ratings`. Provider metadata is stored separately from IMDb ratings, which avoids mislabeling TMDb scores as IMDb scores. Manual movie fields are tracked in JSON and generally protected during rescans.

The database layer lacks an explicit migration ledger and recovery state machine. Migration and restore perform multi-file changes across the database and poster directory without a durable activation journal. This is the source of several recovery and consistency risks described below.

### Feature-to-implementation assessment

| Feature | Audit result | Evidence and limits |
|---|---|---|
| File scanning and FFprobe metadata | Implemented | Real synthetic MKV scan passed; width, streams, bitrate, and status persistence are exercised. Scan race and scaling defects remain. |
| Original filename preservation | Confirmed | `original_filename` is set only on insert and survived rename/relink tests. Incorrect relinks can preserve the wrong identity. |
| IMDb offline titles and ratings | Implemented with correctness defects | Exact title/year matching and staged index replacement work. Locked-ID rating mismatch, cancellation, title parsing, and resource-limit issues remain. |
| TMDb details/posters | Implemented, mocked only | Exact match, cross-host credential redirect refusal, response limits, cast, rating separation, and poster caching exist. No live account/quota/terms test was performed. |
| Gemini fallback | Implemented, mocked only | Suggestions are applied only after TMDb title/year/IMDb confirmation. No live quota/model/Windows credential test was performed. |
| External and embedded subtitles | Implemented | Multiple rows, language/source/translator editing, and manual-language persistence exist. Embedded tracks are delegated to the player rather than explicitly selected by MovieVault. |
| Preferred subtitle playback | Implemented at planning/command level | Paths are validated and mpv/VLC argument lists do not rename files. Actual Windows player launches were not tested. |
| Compound filtering | Confirmed | Language/source/translator share one correlated subtitle row. Release-group collection navigation is not exact. |
| Cast and actor search | Implemented | TMDb cast is stored separately and actor filtering works in synthetic tests. Provider calls are mocked. |
| Smart Update All | Partially robust | Modes and single-job exclusion exist. Cancellation is cooperative and absent from IMDb import/download loops. |
| v1 migration | Implemented but blocked for release | Copy-only staging and empty-target guards exist. Credential sanitization, real-v1 compatibility, and interruption recovery are insufficient. |
| Backup and restore | Implemented but blocked for release | SQLite snapshots and member allowlists exist. Pre-stage DB validation and poster-set atomicity are insufficient. |
| Desktop/WebView safety | Structurally guarded | The native window is private on the JS bridge. No real Windows move/resize/threading test was performed. |
| Themes and UI | Browser-confirmed | A live local server rendered one movie and one subtitle, persisted Midnight theme, and raised no JavaScript errors. Native WebView rendering remains untested. |
| Diagnostics/privacy | Mostly sound | Synthetic redaction and archive exclusion tests pass. Redaction is defense-in-depth rather than comprehensive token/path detection. |
| Windows installer/update | Script-only | Separate AppId/path are present. No build/install/update/uninstall execution was performed, and build/version defects remain. |

## 2. Confirmed bugs

### Final classification of the eight reproducible runtime defects

All eight runtime defects were independently rerun on 2026-10-05 against the audited source commit with isolated, synthetic data. The targeted harness reproduced **8/8 defects in 6.335 seconds**. High severity is reserved here for a confidentiality or startup-availability failure in a normal migration/restore workflow that has no in-app recovery. Medium severity covers deterministic integrity, identity, or workflow failures with a narrower trigger or practical workaround and no modification of original movie files.

| ID | Final severity | Release blocker | Classification basis |
|---|---|---:|---|
| MV-AUD-001 | **High** | **Yes** | Breaks the explicit credential-isolation promise and can propagate legacy secrets into v2 backups. |
| MV-AUD-002 | **High** | **Yes** | A shaped but corrupt backup is staged and can prevent every subsequent normal startup until manual filesystem recovery. |
| MV-AUD-003 | **Medium** | No | Misassociates cached artwork across restored catalogs; the restored database and original movie files remain intact. |
| MV-AUD-004 | **Medium** | No | A common filesystem race aborts a scan, but the failure does not alter original media and the catalog remains reopenable. |
| MV-AUD-005 | **Medium** | No | Cancellation is falsely reported while the complete IMDb index commits; impact is limited to generated metadata. |
| MV-AUD-006 | **Medium** | No | Stored IMDb identity and displayed rating can disagree until rematched or manually corrected. |
| MV-AUD-007 | **Medium** | No | A sampled-hash collision can attach catalog metadata to the wrong file; original movie bytes are not modified. |
| MV-AUD-008 | **Medium** | No | Leading-year titles receive incorrect parsed metadata and fail automatic matching until corrected. |

### Targeted reproduction evidence

The rerun used a temporary Python harness outside the repository. It generated all SQLite databases, ZIP files, poster images, IMDb rows, and dummy video bytes under `/tmp`; it made no provider calls and accessed no personal files.

| ID | Synthetic trigger | Exact observed result |
|---|---|---|
| MV-AUD-001 | Schema-2 source with `settings('tmdb_token','SYNTHETIC_LEGACY_SECRET')`; stage and activate into an empty v2 catalog. | The target retained the exact credential row and value. |
| MV-AUD-002 | Valid product/schema manifest plus `movievault.sqlite` containing `not a sqlite database`. | Staging succeeded; activation raised `DatabaseError: file is not a database`; `restore_pending.zip` still existed after failure. |
| MV-AUD-003 | Source movie ID 1 with a red TMDb poster excluded from its backup; destination movie ID 1 with a blue manual poster. | After restore, movie ID 1 described the source movie but served the destination's pre-restore blue poster. |
| MV-AUD-004 | `os.walk` enumerated one video that was deleted immediately before `Path.stat()`. | Job state was `failed` with `UnboundLocalError: cannot access local variable 'old' where it is not associated with a value`. |
| MV-AUD-005 | 60,000-row IMDb title import; a controlled per-row delay ensured cancellation was requested after the first 3,000-row batch. | Cancellation returned `accepted=True`; final state was `cancelled`; result and live database both contained all 60,000 rows. |
| MV-AUD-006 | Movie locked to `tt2222222`/4.2; exact title/year candidate `tt1111111`/9.9. | Stored ID remained `tt2222222`, but the displayed rating became 9.9 from `tt1111111`. |
| MV-AUD-007 | Two 1,000,000-byte files with different full SHA-256 digests and one differing byte at offset 200,000, outside sampled regions. | Sampled fingerprints matched; the second file was relinked to the first row, retaining the first file's original identity and year. |
| MV-AUD-008 | Parse `1917 (2019).mkv` and `2001 A Space Odyssey (1968).mkv`. | Results were title `1917 (2019)`, year 1917 and title `2001 A Space Odyssey (1968)`, year 2001. |

### MV-AUD-001 — High — v1 migration imports legacy credentials from SQLite settings

**Location:** `mv_migration.py:122-165`, especially the whole-database snapshot and the limited cleanup at lines 152-159.

The migration copies the complete v1 database and resets only `poster_provider` and `gemini_model`. It does not remove secret-bearing legacy settings such as `tmdb_token`, `api_key`, or other credential rows. The manifest still records `no_credentials: true`, and the UI states that no credentials will be imported.

**Reproduction:** Create a schema-2 compatible synthetic legacy database, insert `settings('tmdb_token', 'SYNTHETIC_LEGACY_SECRET')`, stage and apply migration, then query the target. The target retained the row and value.

**Impact:** A legacy credential can be copied into v2 and then included in ordinary v2 backups. This violates a direct privacy promise and can prolong the lifetime of revoked or active credentials.

**Required remediation:** Define an explicit allowlist of migratable setting keys, delete known legacy credential keys and secret-shaped unknown keys from the staged copy, verify the staged database contains no credential material, and add an upgrade-safe cleanup for already migrated v2 databases. Never modify the v1 source.

### MV-AUD-002 — High — corrupt database backup is staged and causes a persistent startup failure

**Location:** `mv_core.py:1068-1113`.

`validate_backup()` checks member names, declared sizes, symlink bits, product, and schema, but does not extract and integrity-check the database. `stage_restore()` therefore accepts a ZIP containing `manifest.json` and arbitrary bytes named `movievault.sqlite`. `process_pending_restore()` fails on the next launch; the pending ZIP remains, so every launch retries before the UI becomes available.

**Reproduction:** A synthetic ZIP with a valid MovieVault manifest and `movievault.sqlite` containing `not a sqlite database` was accepted by `stage_restore()`. `process_pending_restore()` then raised `DatabaseError: file is not a database`; `restore_pending.zip` remained. An immediate second attempt also collided with the already-created timestamped safety backup.

**Impact:** A user-selected damaged or malicious backup can make the app unavailable until files are manually removed. The current live database was preserved in the reproduction, but normal recovery is not exposed in the UI.

**Required remediation:** Fully extract to a bounded temporary directory during staging, run ZIP CRC checks, `PRAGMA integrity_check`, schema/table checks, and application-level invariants before creating `restore_pending.zip`. On activation failure, quarantine the pending archive, preserve the live database, write a non-sensitive recovery record, and allow the app to start.

### MV-AUD-003 — Medium — restore can attach a stale poster to a different restored movie

**Location:** `mv_core.py:1059-1064` and `mv_core.py:1092-1112`.

Backups intentionally omit TMDb cached images while retaining database poster references. During restore, the existing poster directory is replaced only when the archive contains a `posters/` directory. If it contains none, old files remain. Numeric poster names are movie IDs, so an old `posters/1.jpg` can be served for restored movie ID 1 even when it belongs to a different prior catalog.

**Reproduction:** Back up a source catalog whose movie 1 has a red TMDb poster; the ZIP correctly excludes `posters/1.jpg`. Restore it over a destination catalog whose movie 1 has a blue manual poster. After restore, the database describes the source movie and `poster_source='TMDb'`, but `poster_bytes(1)` returns the destination's blue image.

**Impact:** Artwork can be silently misassociated across catalogs, violating backup integrity and potentially exposing an image from the previous catalog.

**Required remediation:** Treat the restored database and poster set as one staged generation. Always replace or clear the destination poster cache, then clear database poster references for every absent archive member before activation. Activate with a durable marker and recover safely from interruption.

### MV-AUD-004 — Medium — a file disappearing during scan aborts the entire job

**Location:** `mv_core.py:521-581`.

The exception handler reads `old`, but `old` is assigned only after `fp.stat()`. If a file is enumerated and disappears before `stat`, the handler raises `UnboundLocalError` instead of recording a failed file and continuing.

**Reproduction:** Yield one video from a synthetic `os.walk`, delete it before `fp.stat()`, and run a scan. The job ended `failed` with `UnboundLocalError: cannot access local variable 'old' where it is not associated with a value`.

**Impact:** Normal library churn, network shares, removable media, or antivirus activity can abort a complete scan.

**Required remediation:** Initialize `old = None` before the first fallible operation and add race tests for deletion, rename, permission loss, and drive disconnect at each scan phase.

### MV-AUD-005 — Medium — cancelling an IMDb import does not stop it and still commits all data

**Location:** `mv_core.py:932-1010` and job state logic at `mv_core.py:648-676`.

IMDb title and ratings import loops never inspect `job['cancel']`. The generic job wrapper labels the operation `cancelled` after the function returns, even if it completed and committed all records.

**Reproduction:** Start a 60,000-row synthetic IMDb import and immediately call `cancel_job()`. Cancellation was accepted; the final job state was `cancelled`, but the result reported 60,000 imported titles and the live database contained all 60,000 rows.

**Impact:** The UI provides false cancellation semantics during the largest disk/CPU operation. Users cannot stop an accidental import and may believe no changes were committed.

**Required remediation:** Check cancellation between bounded batches, keep work in the staging database, avoid replacing the live index on cancellation, and distinguish `completed`, `cancelled_without_commit`, and `completed_before_cancel` states.

### MV-AUD-006 — Medium — locked IMDb ID can display a rating from a different IMDb title

**Location:** `mv_core.py:890-903` and `mv_core.py:1030-1041`; the scan path has the same pattern at lines 559-565.

When a user manually locks `imdb_id`, exact title/year matching may find another IMDb row. The code correctly avoids replacing the locked ID, but still writes the matched row's rating.

**Reproduction:** A movie locked to `tt2222222` had rating 4.2. The offline title index contained an exact title/year match `tt1111111` with rating 9.9. `match_imdb()` retained `tt2222222` but set `imdb_rating` to 9.9 and returned the other ID as the match.

**Impact:** Movie identity and displayed IMDb rating disagree, undermining metadata trust.

**Required remediation:** If `imdb_id` is locked/present, ratings must come only from that ID. An exact title/year candidate may be offered for review but must not update identity-dependent fields.

### MV-AUD-007 — Medium — sampled fingerprint can relink a different file as the same movie

**Location:** `mv_core.py:52-60` and `mv_core.py:541-572`.

The fingerprint hashes file size plus only the first, middle, and last 64 KiB. Different same-size files can share those sampled regions. The relink path treats a unique unavailable fingerprint match as identity proof.

**Reproduction:** Two distinct 1,000,000-byte synthetic files differed at byte 200,000, outside sampled regions, and produced the same fingerprint despite different full SHA-256 digests. After scanning `First Identity (2001).mkv`, deleting it, and adding `Second Identity (2022).mkv`, MovieVault relinked the same row: original/display identity stayed “First Identity” while the current file became “Second Identity”.

**Impact:** Notes, ratings, preferred subtitles, and identity metadata can be attached to the wrong media file. Movie bytes are not modified.

**Required remediation:** Use the sampled hash only to shortlist candidates, then verify a full cryptographic digest before relinking. Store the stronger identity additively so existing catalogs remain compatible.

### MV-AUD-008 — Medium — titles beginning with a year are parsed with the wrong release year

**Location:** `mv_core.py:32-50`.

The parser selects the first four-digit year anywhere in the stem. If that year is the title, the title prefix is empty and the fallback keeps the full stem while retaining the title-year as release year.

**Reproduction:** `1917 (2019).mkv` parsed as title `1917 (2019)`, year `1917`; `2001 A Space Odyssey (1968).mkv` parsed as title `2001 A Space Odyssey (1968)`, year `2001`.

**Impact:** Well-known titles fail exact IMDb/TMDb matching and receive incorrect year filtering until manually corrected.

**Required remediation:** Prefer a trailing/bracketed year token, add exceptions for leading numeric titles, and cover ambiguous filenames without weakening conservative matching.

### MV-AUD-009 — Low — release-group collections use broad search and include unrelated movies

**Location:** `web/app.js:24-27`, `web/app.js:37-38`, and `mv_core.py:357-359`.

Clicking a collection sets `state.group`, but `queryOptions()` sends it as the general `q` parameter. General search also matches title, original filename, genres, cast, and year.

**Reproduction:** A catalog with one `release_group='YTS'` movie and one `release_group='OTHER'` movie named `YTS Documentary.mkv` reported one YTS group member, while the UI-equivalent `movies(q='YTS')` returned both rows.

**Impact:** Collections are not reliable release-group views.

**Required remediation:** Add an exact, parameterized `release_group` filter and send that from collection navigation.

### MV-AUD-010 — Medium — Windows build wrapper can mask PowerShell build failure

**Location:** `BUILD_WINDOWS.cmd:1-9`.

After PowerShell fails, the wrapper runs `pause` but does not execute `exit /b 1`. The batch exit code can therefore become the successful `pause` result rather than the failed build result.

**Impact:** CI or a human wrapper can report success even though dependency installation, tests, packaging, or installer compilation failed.

**Required remediation:** Capture `%ERRORLEVEL%` immediately after PowerShell and exit with that code after any message/pause. Verify on Windows in both interactive and noninteractive shells.

### MV-AUD-011 — Medium — release identifiers disagree across runtime, docs, tests, archive, and installer

**Locations:** `mv_core.py:13` reports `2.0.0-rc.2`; `README_AR.md` mixes RC1 and RC2; `START_HERE.txt` says RC1; `tests/visual_smoke.py:6` injects `2.0.0-rc.1`; `build_windows.ps1` and `MovieVault.iss` produce RC1-named artifacts while the installer advertises 2.0.0.

**Impact:** Support reports, upgrades, screenshots, and distributed filenames cannot reliably identify the code being run. This increases update and rollback risk.

**Required remediation:** Generate runtime, installer, artifact, test, and documentation versions from one release metadata source and test their equality before packaging.

### MV-AUD-012 — Low — optional visual QA rewrites tracked documentation screenshots

**Location:** `tests/visual_smoke.py:25-39`.

The test writes directly to tracked files under `docs/`. Running `qa_runner.py` in a checkout with Playwright can therefore dirty the repository and overwrite review artifacts.

**Impact:** QA has hidden side effects and can obscure meaningful screenshot changes.

**Required remediation:** Write test output to a timestamped ignored artifact directory and compare against approved baselines explicitly when visual regression testing is intended.

## 3. Missing or incomplete features

The following are documented as deferred or remain incomplete; they should not be advertised as finished:

- Grouping multiple editions under one movie card.
- A dedicated duplicate detector and safe duplicate/relink resolution workflow.
- A detailed recently-watched timeline.
- Automated native Windows desktop and installer UI tests.
- General merge of two nonempty catalogs; migration intentionally requires an empty v2 target.

Additional implementation/UI gaps found during the audit:

- Custom subtitle sources can be removed through the backend, but the UI only adds and lists them.
- The backend supports importing an already-downloaded IMDb ratings file, but the UI exposes only automatic ratings download.
- The backend supports a watched filter, but the advanced-filter UI does not expose it.
- `archive_missing` remains a stored setting but is not used by scanning; the UI correctly presents retention as always on, so the stored toggle is dead configuration.
- Embedded subtitle tracks are cataloged, but MovieVault cannot choose a specific embedded stream; selection is left to the player.
- Gemini model discovery selects one model automatically; the UI does not let the user choose among returned compatible models.

## 4. Security findings

### Positive controls confirmed in source

- SQL values are parameterized; dynamic SQL fragments are selected from fixed allowlists or validated field sets.
- FFprobe, FFmpeg, VLC, mpv, and platform launchers receive argument arrays; no `shell=True`, `eval`, `exec`, pickle, or unsafe YAML path was found.
- The HTTP service binds only to IPv4 loopback. API calls require a random per-run header token and validate Host; browser requests with Origin are restricted to the active loopback origin.
- Provider secrets are not returned by status/bootstrap APIs. Current v2 credentials live outside SQLite, use DPAPI on Windows, and remain memory-only on Linux development systems.
- TMDb/Gemini authenticated redirects are restricted to HTTPS on the same host.
- Poster uploads are decoded and re-encoded by Pillow with pixel and byte limits. Managed poster reads constrain resolved paths to the poster directory.
- External subtitle playback rejects traversal, symlinks, unsupported extensions, and subtitles not belonging to the selected movie.
- ZIP imports use member allowlists, declared-size limits, and symlink rejection.
- Frontend catalog/provider values are escaped before dynamic HTML insertion.
- Diagnostic exports exclude the raw database and credential files, and production event calls currently use controlled metadata rather than request bodies.

### Confirmed security issue

- **MV-AUD-001** is a confidentiality defect: legacy credentials stored in SQLite can cross the migration boundary and enter backups.

### Potential risks requiring hardening or platform validation

- The unauthenticated `/` page serves the session token and static routes do not validate Host. API Host validation blocks straightforward DNS-rebinding writes, but the tokenized artwork route also lacks Host validation. Apply Host checks consistently to all token-bearing and artwork responses.
- CSP permits `'unsafe-inline'` for scripts and styles. Current escaping reduces exploitability, but removing inline script/event dependencies would make the token-bearing page more resilient to future XSS regressions.
- Diagnostic redaction recognizes labeled secrets, Bearer values, and Gemini-style `AIza` keys, but it is not a general detector for JWT-like TMDb tokens or arbitrary Windows paths. Keep production log fields allowlisted and add adversarial export tests.
- Full backups contain the complete catalog, notes, root paths, filenames, and manual metadata by design and are not encrypted. The UI should state that backup ZIPs are sensitive personal data.
- IMDb downloads rely on HTTPS but do not pin the final hostname after redirects or verify a published digest. This is lower risk than credential-bearing redirects, but it affects metadata integrity.
- Windows dependencies are version-ranged without a lockfile or hashes, the build upgrades pip at build time, and release binaries are not signed in the provided workflow. Reproducibility and supply-chain controls are insufficient for public distribution.
- DPAPI behavior, inherited ACLs, credential deletion, and memory lifetime must be verified on real Windows user profiles.

## 5. Performance findings

### Confirmed scan scaling bottleneck

For every movie, `detect_subtitles()` lists the entire containing directory, and `_local_poster()` lists it again. A flat directory therefore performs approximately quadratic directory-entry work. With fingerprinting and FFprobe mocked to constant time, synthetic scans measured:

| Movies in one folder | Elapsed |
|---:|---:|
| 200 | 0.524 s |
| 400 | 1.812 s |
| 800 | 6.433 s |

Doubling from 400 to 800 increased elapsed time by 3.55×. Build one directory index per folder per scan and share it between subtitle and poster detection.

### Other material performance risks

- FFprobe runs sequentially with a 25-second timeout per changed file. A large set of slow, damaged, or network-hosted files can take hours; cancellation waits for the current subprocess timeout.
- IMDb imports and gzip decompression have no decompressed-byte/row/time bound and ignore cancellation. A small compressed input can generate very large staging databases.
- Scan opens several SQLite connections per file and repeatedly reads settings inside subtitle detection. Batching writes and caching immutable scan settings would reduce overhead.
- Full `raw_probe` JSON is retained per movie. Large stream/tag payloads can substantially grow the database and backups; define a safe size cap while preserving useful technical data.
- `stats()` performs full aggregate scans and is called frequently by UI refreshes. It is acceptable for small libraries but needs measurement at 10,000-100,000 rows.
- Title, cast, genre, and filename searches use leading-wildcard `LIKE`, so indexes cannot accelerate them. Consider FTS only after correctness work and with an additive migration.
- TMDb metadata/poster expiry scans all matching rows at every `Catalog` construction. This is likely acceptable at current scale but should be included in startup benchmarks.

## 6. Existing automated test quality

### What the 50 tests do well

- Use isolated temporary SQLite databases and synthetic media rather than user data.
- Exercise a real FFprobe scan for the bundled small MKV.
- Verify original filename persistence, rename relink, Missing vs Offline, manual subtitle-language persistence, same-row subtitle predicates, basic backup/restore, basic migration, poster path safety, and argument-list playback.
- Mock provider responses with exact/ambiguous match cases, response limits, licensing checks, credential non-echo, and authenticated redirect protection.
- Include a regression guard for the private pywebview window field.
- Check browser happy paths for cards, settings panels, theme changes, subtitle editing controls, modal navigation, and Smart Update UI.

### Weaknesses and false-confidence areas

- “Legacy” fixtures are created by the current v2 `Catalog` and then have their schema number changed. They are not evidence of compatibility with the real v1 schema or real v1 backups.
- TMDb, Gemini, Commons, VLC/mpv, DPAPI, WebView2, PyInstaller, and Inno Setup behavior is mocked or inspected as text.
- The visual test stubs every API and returns `{ok: true}` for unknown calls; it does not validate browser/server contracts, error rendering, polling failures, authentication expiry, or real database state.
- Installer tests only search for strings in `MovieVault.iss`; they do not build, install, upgrade, uninstall, or execute `--backup-only`.
- Background tests wait for success but rarely test cancellation, process termination, simultaneous requests, or recovery.
- There is no coverage report, property/fuzz testing, migration compatibility corpus, fault injection suite, or performance gate.
- The optional visual test changes tracked files.

### High-priority missing automated tests

1. Real sanitized v1 database and backup fixtures for each supported v1 schema, including legacy credential storage and unknown settings.
2. Corrupt SQLite, ZIP CRC failure, truncated ZIP, missing tables/columns, incompatible schema, and activation interruption at every database/poster move.
3. Restore into catalogs with overlapping movie IDs, no archived posters, TMDb-only posters, mixed poster sources, and orphan poster files.
4. File deletion/rename/permission loss between enumeration, stat, fingerprint, FFprobe, subtitle discovery, and commit.
5. Root disconnect during enumeration, partial network-share failure, Windows path case variants, long paths, Unicode normalization, and inaccessible subdirectories.
6. Full-hash verification for relink candidates, duplicate copies, identical editions, same-size sampled collisions, moves across roots, and two unavailable candidates.
7. Titles beginning with years, multiple year tokens, episodic names, non-Latin titles, alternate cuts, and filenames without a year.
8. Manual IMDb ID plus conflicting exact title match; duplicate IMDb rows; malformed/oversized gzip; cancellation before and after live-index replacement.
9. Job start/cancel races, shutdown during each background operation, poster upload concurrent with poster fetch, and state restoration after restart.
10. mpv and VLC command behavior on Windows with spaces, Unicode, `.idx/.sub` pairs, no player installed, embedded-only subtitles, and player launch failure.
11. Provider 401/403/429/5xx, timeout, malformed JSON, redirect, image decompression-bomb, expired cache, attribution, and quota recovery tests.
12. Diagnostic export tests for JWT-like tokens, arbitrary drive paths, UNC paths, email addresses, malformed logs, and concurrent rotation/export.
13. Real local-server Playwright tests for success and failure paths, plus accessibility/keyboard/focus tests.
14. Windows build smoke, packaged static assets, clean install, RC-to-next-version upgrade, backup-hook failure, uninstall retention, and v1 side-by-side operation.

## 7. Windows-specific risks

The following require real Windows 10 and Windows 11 execution and remain unverified:

- pywebview/WebView2 startup, move/resize/maximize/minimize loops, DPI scaling, multiple monitors, modal focus, clipboard, file dialogs, and shutdown.
- DPAPI save/read/delete under the same user, failure under another user, profile migration, ACL inheritance, and packaged-runtime behavior.
- Path case-insensitivity, UNC/network shares, disconnected drive letters, removable-drive reconnects, long paths, reserved names, and non-ASCII paths.
- FFprobe/FFmpeg discovery from bundled `vendor`, subprocess window suppression, timeout behavior, and codec support of the selected distribution.
- Actual VLC/mpv discovery and CLI semantics for external subtitle selection and subtitle suppression.
- PyInstaller collection of WebView2/pythonnet dependencies and operation on a clean machine without developer runtimes.
- Inno Setup compile, `--backup-only` upgrade hook, locked-running-app behavior, same-AppId upgrade, rollback on backup failure, uninstall retention, shortcuts, and side-by-side v1 operation.
- Portable ZIP extraction and launch from paths containing spaces and non-Latin characters.
- Installer/release signing, SmartScreen reputation, file version metadata, license notices, and FFmpeg redistribution obligations.

## 8. Prioritized remediation roadmap

### P0 — the two confirmed release-blocking defects

1. Sanitize migrated settings with an explicit allowlist; add real-v1 fixtures and a safe cleanup migration for already imported credentials.
2. Fully validate backup databases before staging; quarantine invalid pending restores, add durable activation/recovery markers, and always allow startup with the current catalog.

### P1 — data integrity and runtime correctness

1. Make database + poster restoration a staged generation with deterministic clearing of absent poster references and interruption recovery.
2. Fix the scan disappearance race and add phase-by-phase filesystem fault injection.
3. Verify a full content hash before fingerprint relink and migrate existing rows additively.
4. Make IMDb import/download cancellation real, transactional, and accurately reported.
5. Keep IMDb ratings bound to the stored/locked IMDb ID.
6. Correct year-leading title parsing and add a filename corpus.
7. Add concurrency protection for poster cache writes and other synchronous API changes that can overlap background jobs.

### P2 — release engineering and scale

1. Add an exact release-group API filter.
2. Index folder entries once per scan and batch database work; establish 1k/10k synthetic-library budgets.
3. Bound decompressed IMDb input and `raw_probe` storage.
4. Unify version metadata and make `BUILD_WINDOWS.cmd` propagate failure.
5. Lock/hash build dependencies, produce an SBOM, sign Windows artifacts, and verify packaged contents.
6. Move visual-test artifacts out of tracked documentation and add live-server failure-path E2E tests.
7. Harden Host checks, CSP, diagnostic redaction, and backup sensitivity messaging.

### Release acceptance gate

Build and run the packaged application on the Windows matrix before distributing an installer. This is a mandatory release prerequisite caused by the current evidence gap, rather than a third confirmed runtime defect.

## 9. Features requiring real Windows verification

Before release, execute every item in `docs/QA_CHECKLIST_AR.md` on disposable Windows profiles, with special emphasis on:

- clean v2 install beside a working v1 installation;
- migration from a real backed-up v1 database via auto-detect, selected app folder, direct DB, and ZIP;
- WebView2 stability while moving/resizing and using nested modals;
- DPAPI persistence and credential removal;
- removable-drive Offline/Missing transitions during active scans;
- VLC/mpv subtitle selection without any filename change;
- trusted bundled FFprobe/FFmpeg technical metadata and frame-poster generation;
- packaged backup, staged restore, crash/restart, and recovery;
- portable ZIP and Inno Setup clean install, upgrade, failed backup hook, uninstall, and retained v2 data;
- live TMDb/Gemini calls with disposable credentials and explicit quota/rate-limit cases.

## 10. Validation performed during this audit

- `PYTHONPYCACHEPREFIX=/tmp/movievault-pycache /workspace/movievault-env/bin/python -W error::ResourceWarning -m unittest discover -s tests -q` — **50 tests passed in 5.852 seconds**.
- `node --check web/app.js` — **passed**.
- `/workspace/movievault-env/bin/python -m pip check` — **passed; no broken requirements**.
- Live local-server Playwright smoke with a real temporary SQLite catalog and real API calls — **1 movie card, 1 subtitle row, Midnight theme persisted, zero JavaScript page errors**.
- Targeted synthetic runtime-defect harness rerun on 2026-10-05 — **8/8 reproduced in 6.335 seconds**, covering MV-AUD-001 through MV-AUD-008 with the exact outcomes recorded above.
- Separate synthetic release-group reproduction — confirmed MV-AUD-009; MV-AUD-010 through MV-AUD-012 were confirmed by deterministic source/build-path inspection.
- Synthetic flat-folder scan benchmark — 200/400/800 results shown above.
- Static inspection of all Python, JavaScript, HTML/CSS, documentation, tests, PowerShell, batch, and Inno Setup source.

No personal movie files, real credentials, or external provider accounts were used. All audit fixtures were temporary and synthetic. Application source code was not modified as part of the audit.

## 11. Release-readiness decision

**Decision: No-go for a stable public release or migration of irreplaceable user data.**

The application is suitable for continued source-preview development with disposable data. The current automated suite demonstrates useful baseline behavior, and the architecture has several sound safety choices. The two defect-level release blockers are MV-AUD-001, because migration can violate credential isolation, and MV-AUD-002, because a staged corrupt restore can prevent startup. Poster misassociation and the other Medium/Low findings remain required correctness work under the priorities above. The unexecuted Windows package matrix is a separate release-acceptance prerequisite, not an additional confirmed defect.

Complete all P0 items, add regression tests for every confirmed defect, run the real-v1 compatibility corpus, and pass the Windows release matrix before promoting beyond release-candidate source preview. Preserve existing v1 and v2 data through additive schema changes, staged copies, explicit backups, and failure-recovery tests; do not repair these issues by deleting, resetting, or silently rewriting user catalogs.
