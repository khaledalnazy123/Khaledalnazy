# P2C security hardening and live-server E2E remediation

This batch is limited to local HTTP trust boundaries, browser policy, diagnostic
privacy, backup sensitivity messaging, QA artifact hygiene, and real local-server
browser coverage. It does not change installer/build engineering, scan
performance, catalog features, or provider behavior.

Implemented:

- centralized pre-dispatch validation of exactly one `Host` header on every
  request, limited to `127.0.0.1:<bound port>` or
  `localhost:<bound port>` with case-normalized hostname;
- Host validation before the token-bearing root document, static assets,
  favicon, artwork, API and not-found handling; artwork continues to require
  the ephemeral session token as well;
- strict response headers: self-only scripts/styles/connect, no inline/eval
  escape hatch, denied framing, no base/object embedding, no referrer,
  `nosniff`, and `no-store`; HSTS is intentionally omitted on plain loopback
  HTTP;
- removal of inline styles and event handlers from static and generated UI;
- generic safe HTTP 500 responses, with only the safe route and exception class
  retained in local diagnostics;
- consistent safe HTTP 409 handling when an authenticated root-disable DELETE
  conflicts with exclusive catalog maintenance, followed by normal retry;
- redaction for JWT-shaped values, drive-letter paths using either separator,
  UNC paths, common Unix/macOS absolute paths, email-like values, and standalone
  movie/subtitle filenames;
- explicit pre-creation, post-creation and restore messaging that full backups
  contain sensitive catalog metadata, are unencrypted/non-anonymized, exclude
  videos and provider credentials, and must be stored/shared carefully;
- generated visual outputs moved to ignored `qa_reports/visual`; the five
  historical generated files under `docs/` were removed from source control;
- deterministic raw HTTP, static-policy, privacy, backup-copy, artifact, and
  real Chromium/live-`MovieServer` regressions using only temporary synthetic
  data and no external provider calls.

Validation on Linux/Python 3.12.14:

- dedicated P2C: **29/29 passed**, including **3/3** real live-server Chromium
  E2E tests;
- full suite: **148/148 passed**;
- strict full suite with `ResourceWarning` promoted to error: **148/148 passed**;
- Python compileall and JavaScript syntax: **passed**;
- CSP/static audit, raw Host-header probes, adversarial diagnostic ZIP scan,
  backup sensitivity copy checks, and tracked-artifact checks: **passed**;
- existing Playwright visual smoke: **passed**, with output only in ignored QA
  storage;
- `qa_runner.py`: **PASS**, including the full suite, compilation, and visual
  smoke.

The real browser tests used Chromium against a live server bound to an ephemeral
`127.0.0.1` port and a temporary `Catalog`. They exercised root/bootstrap,
movies, details, settings, static assets, token handling, invalid input,
not-found data, artwork authorization, busy conflict, a controlled provider
failure, navigation recovery, and page/console/CSP monitoring. They did not call
real TMDb, Gemini, or IMDb endpoints.

No Windows-specific acceptance was executed. Windows WebView2, DPAPI, packaged
EXE/installer, Authenticode, SmartScreen, and real provider credentials remain
outside this batch and require separate Windows acceptance.
