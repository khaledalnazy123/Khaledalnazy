# P1A Library Integrity Remediation

This batch addresses only MV-AUD-003, MV-AUD-004, and MV-AUD-007 from `CODEX_INITIAL_AUDIT.md`. P0 protections remain in place; IMDb, filename parsing, installer, UI, and other P1/P2 work are outside this change.

## MV-AUD-003 — restore poster generation integrity

- Restore extraction always creates a complete staged poster directory, including when the archive contains zero poster members.
- Before activation, the staged database clears poster metadata for every movie whose expected numeric poster member is absent. This covers TMDb cache artwork intentionally omitted from backups.
- Orphan poster members without a matching database reference are discarded from the staged generation.
- Activation always replaces the previous live poster directory with the staged generation, preventing overlapping movie IDs from reusing stale artwork.
- The existing database/poster rollback path remains active if either part of generation activation fails.

## MV-AUD-004 — scan file-race isolation

- Scan resolves the existing catalog row before fallible file operations. A file that disappears, moves, or becomes unreadable can therefore be retained without being misclassified during that partial scan.
- Each affected file increments `failed_files`, records a privacy-safe `scan_file_skipped` diagnostic containing only root ID, phase, and exception class, and allows the wider root scan to continue.
- A completed root scan containing individual file failures records `scan_partial`; unrelated catalog rows are still scanned and retained.

## MV-AUD-007 — fingerprint relink verification

- The sampled fingerprint remains only a candidate shortlist key.
- A new additive `content_sha256` movie column stores a full-file SHA-256 digest. Existing catalogs gain it through the normal additive initialization path, and unchanged legacy rows are backfilled when next scanned.
- Relinking to a different path requires exactly one absent candidate with the same nonempty full digest. Missing legacy digests, digest mismatches, and multiple full-digest matches do not auto-relink.
- Identity verification reads media only; it does not rename, delete, or rewrite movie files.

## Verification

- Dedicated P1A regression tests: **5/5 passed** with `ResourceWarning` promoted to an error.
- Full unit/integration suite: **64/64 passed in 6.436 seconds**.
- Strict full suite: **64/64 passed in 6.606 seconds** with `ResourceWarning` promoted to an error.
- Python compilation: **PASSED**.
- Automated QA runner: **PASS** for 64 unit/integration tests, Python compilation, and Playwright visual smoke. See `qa_reports/QA_20261005_140703.txt` and `.json`.
- A separate Playwright visual smoke run passed with three movie cards, settings panels, two subtitle rows, modal navigation, and no page errors.

No Windows, WebView2, DPAPI, packaged executable, installer, VLC/mpv, or live provider verification was performed in this batch.
