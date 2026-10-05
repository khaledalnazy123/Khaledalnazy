# P0 Release-Blocker Remediation

This change addresses only MV-AUD-001 and MV-AUD-002 from `CODEX_INITIAL_AUDIT.md`.

## MV-AUD-001 — legacy credential migration

- v1 migration now retains only the explicit `MIGRATABLE_SETTING_KEYS` preference allowlist. Unknown settings and credential-bearing rows never leave the private staged copy.
- Provider and AI state are reset to safe disconnected defaults because credentials remain in the original profile.
- Activation sanitizes older `migration_pending` snapshots again, covering imports staged by a vulnerable build.
- Catalog startup performs a one-time cleanup when `v1_imported_at` exists without the sanitization marker. It preserves the known current v2 preference allowlist and removes every other legacy row before APIs or backup creation can use the database.
- The original v1 database is always opened read-only and is never cleaned or rewritten.

## MV-AUD-002 — corrupt restore startup failure

- `stage_restore()` copies to a private partial file and validates that exact copy before it can become `restore_pending.zip`.
- Validation enforces archive and extracted-size bounds, member allowlists, duplicate/symlink rejection, compression-ratio limits, full ZIP CRC verification, a bounded database extraction, product/schema compatibility, SQLite `integrity_check`, required tables, and agreement between manifest and database schema versions.
- Activation validates and extracts again, snapshots the current live database, and rolls the database and poster directory back if any activation step fails.
- A failed pending restore is moved to `restore_quarantine`, a recovery event records only the exception class and quarantine status, and `process_pending_restore()` returns without blocking normal startup.

## Verification

- Dedicated P0 regression and fault-injection tests: **7/7 passed**.
- Full unit/integration suite: **57/57 passed**.
- Automated QA runner: unit/integration, Python compilation, and Playwright visual smoke all passed. See `qa_reports/QA_20261005_094324.txt` and `.json`.
- Windows-specific acceptance remains pending; no Windows result is claimed.
