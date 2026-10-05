# P0 Release-Blocker Remediation

This change addresses only MV-AUD-001 and MV-AUD-002 from `CODEX_INITIAL_AUDIT.md`.

## MV-AUD-001 — legacy credential migration

- v1 migration now retains only the explicit `MIGRATABLE_SETTING_KEYS` preference allowlist. Unknown settings and credential-bearing rows never leave the private staged copy.
- Provider and AI state are reset to safe disconnected defaults because credentials remain in the original profile.
- Activation sanitizes older `migration_pending` snapshots again, covering imports staged by a vulnerable build.
- Catalog startup performs a one-time cleanup when `v1_imported_at` exists without the sanitization marker. It preserves the known current v2 preference allowlist and removes every other legacy row before APIs or backup creation can use the database.
- Restore activation applies the same current-v2 setting allowlist to every private restore candidate marked as a v1 import, even if an older or misleading cleanup marker is present. Sanitization completes before the candidate can replace the live database, so the running `Catalog`, APIs, backups, and provider logic cannot observe restored legacy secret rows.
- The original v1 database is always opened read-only and is never cleaned or rewritten.

## MV-AUD-002 — corrupt restore startup failure

- `stage_restore()` copies to a private partial file and validates that exact copy before it can become `restore_pending.zip`.
- Validation enforces archive and extracted-size bounds, member allowlists, duplicate/symlink rejection, compression-ratio limits, full ZIP CRC verification, a bounded database extraction, product/schema compatibility, SQLite `integrity_check`, required tables, and agreement between manifest and database schema versions.
- Validation also enforces the minimum required column contract for every core MovieVault table. An integrity-valid database with all expected table names but missing application-required columns is rejected before it can become `restore_pending.zip`.
- Activation validates and extracts again, snapshots the current live database, and rolls the database and poster directory back if any activation step fails.
- A failed pending restore is moved to `restore_quarantine`, a recovery event records only the exception class and quarantine status, and `process_pending_restore()` returns without blocking normal startup.

## Verification

- Dedicated P0 regression and fault-injection tests: **9/9 passed**, including strict `ResourceWarning` handling.
- Full unit/integration suite: **59/59 passed**; a separate full run with `ResourceWarning` promoted to an error also passed **59/59**.
- Automated QA runner: **PASS** for 59 unit/integration tests, Python compilation, and Playwright visual smoke. See `qa_reports/QA_20261005_130912.txt` and `.json`.
- A separate Playwright visual smoke run also passed with three cards, both settings panels, two subtitle rows, modal navigation, and no page errors.
- Windows-specific acceptance remains pending; no Windows result is claimed.
