# P1B IMDb and Filename Correctness Remediation

This batch addresses only MV-AUD-005, MV-AUD-006, and MV-AUD-008 from `CODEX_INITIAL_AUDIT.md`. P0 and P1A protections remain in place; P2, installer, performance, poster concurrency, and unrelated UI work are outside this change.

## MV-AUD-005 — genuine IMDb cancellation

- Title and ratings imports check cancellation throughout their row loops and immediately before live replacement. Ratings and title downloads also check before and after each bounded network read.
- Imported data remains in private staging databases until an explicit transaction atomically replaces the corresponding live IMDb table and records its timestamp.
- Cancellation before that commit raises a dedicated cancellation outcome, preserves the existing live index, and removes staging/download files in `finally` cleanup.
- The job records whether its commit completed. A cancellation request arriving after the atomic replacement can stop optional post-import enrichment, but the final job state remains `completed` because the new live index is already committed.
- Diagnostics and cancellation messages contain operation state only, not dataset paths.

## MV-AUD-006 — IMDb identity and rating consistency

- A shared identity-update helper treats an existing valid IMDb ID as the rating authority. An exact title/year candidate with another tconst cannot supply its rating or other IMDb-index fields.
- Scan enrichment, local metadata refresh, post-import enrichment, manual matching, ratings refresh, and TMDb detail refresh all retain rating/identity consistency.
- Manually changing or clearing an IMDb ID immediately refreshes or clears `imdb_rating` from the exact selected tconst.
- Movies without a stored or manually locked IMDb ID continue to adopt a unique exact title/year match and its rating normally.

## MV-AUD-008 — year-leading filenames

- Filename parsing prefers a bracketed release-year token, then the last of multiple year-like tokens.
- A sole leading four-digit token is treated as part of the title rather than automatically becoming the release year.
- The regression corpus covers `1917 (2019)`, `2001 A Space Odyssey (1968)`, a title consisting only of a year, ordinary titles, multiple year tokens, dotted names, missing years, source/resolution suffixes, and release groups.

## Verification

- Dedicated P1B regression tests: **8/8 passed in 0.134 seconds** with `ResourceWarning` promoted to an error.
- Full unit/integration suite: **74/74 passed in 6.610 seconds**.
- Strict full suite: **74/74 passed in 6.526 seconds** with `ResourceWarning` promoted to an error.
- Python compilation: **PASSED**.
- Automated QA runner: **PASS** for 74 unit/integration tests, Python compilation, and Playwright visual smoke. See `qa_reports/QA_20261005_153909.txt` and `.json`.
- A separate Playwright visual smoke run passed with three movie cards, settings panels, two subtitle rows, modal navigation, and no page errors.

No Windows, WebView2, DPAPI, packaged executable, installer, VLC/mpv, or live-provider verification was performed in this batch.
