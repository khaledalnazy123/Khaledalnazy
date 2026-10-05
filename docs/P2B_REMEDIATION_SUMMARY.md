# P2B Windows release-engineering remediation

This batch is limited to release/version/build correctness. It does not change
network binding, CSP, diagnostics privacy, application UI behavior, or P2A.

Implemented:

- one authoritative semantic version in `VERSION`, with deterministic Windows
  numeric/resource and artifact-name derivation;
- fail-fast CMD/PowerShell behavior with preserved nonzero status;
- complete exact and hash-verified CPython 3.12 x64 build/runtime locks;
- immutable staging and recorded identity/SHA-256 provenance for ffprobe and
  optional ffmpeg;
- SPDX 2.3 JSON SBOM creation and structural validation;
- portable-package allow/deny verification plus a complete SHA-256 manifest;
- genuine external Authenticode/timestamp configuration with mandatory
  verification, or explicit `UNSIGNED` metadata when credentials are absent;
- version-derived portable and setup names and Inno metadata;
- focused Linux regression/fault tests for all of the above.

Validation on Linux/Python 3.12.14:

- dedicated P2B: **16/16 passed** with strict `ResourceWarning` handling;
- full suite: **113/113 passed**;
- strict full suite: **113/113 passed**;
- compileall and JavaScript syntax: **passed**;
- `qa_runner.py`: **PASS**, including Playwright visual smoke;
- both lock structures and their actual hash-checked downloads: **passed** for
  the supported CPython 3.12 x64 target;
- SPDX and synthetic package/manifest verification: **passed**;
- static CMD/PowerShell failure-path regression checks: **passed**.

The Windows build was not executed in this Linux environment. Windows artifact
creation, Authenticode with a real certificate, SmartScreen, WebView2, DPAPI,
installer lifecycle, and hardware-specific acceptance remain unverified and
must be completed on Windows before release. Exact executed Linux results are
recorded in `QA_REPORT.md`.
