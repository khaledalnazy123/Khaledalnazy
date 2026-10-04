# Codex review handoff — MovieVault v2.0 RC2

Role: independent senior Windows software engineer + security/QA reviewer. Read README_AR.md, docs/FEATURE_STATUS.md, docs/MIGRATION_V1_TO_V2_AR.md and docs/KNOWN_LIMITATIONS.md first. All credentials and personal library data are intentionally excluded from this source bundle.

Priorities:
1. Preserve the exact user-facing feature contract; NEVER silently remove/disable a feature to make a test pass.
2. Verify v1 → v2 migration with REAL v1 schema (separate profile; source DB untouched; old app folder chosen, Auto-detect; preview counts; empty-v2 guard; interrupted migration recovery). Back up every database before a potentially destructive step.
3. On Windows 10/11 test Python 3.12 x64, pywebview/WebView2 resizing and moving; do not reintroduce `DesktopApi.window` public attribute (historical recursion/wrong UI thread severe bug).
4. Add/execute unit, integration, pairwise filter, UI E2E and failure tests, especially same-row subtitle source+language intersection, manual override across rescan, background job cancellation, Offline-vs-Missing drives, duplicates/relinks and database/ZIP corruption.
5. Check command execution path/file validation; audit API key protection with DPAPI, localhost ephemeral CSRF token and cross-origin restrictions. Logs/support exports must not contain tokens, user paths or raw databases.
6. Validate TMDb/IMDb license/caching/attribution compliance and Gemini API quota handling. Never replace verified metadata based solely on AI output.
7. Build Windows Portable ZIP and Inno Setup installer with correct v2 AppId independent from v1. Test clean install, v2 upgrade, uninstall retain-data behavior, crash/restart and emergency restore on a temporary Windows profile.
8. Benchmark a synthetic dataset with thousands of movies and multiple subtitles; check UI responsiveness, ffprobe subprocess timeouts, poster sizes/expiration and cancellation.
9. Deliver a CHANGES.md and QA_REPORT.md with exact tested commands, outcomes, blockers and any remaining known risks. Distinguish executable validation from mocks.

Do not ask for actual API tokens or the user's private movie database. Use mocks or a separate local disposable test account. Start by running `py -3.12 -m unittest discover -s tests -v` on Windows, then use `BUILD_WINDOWS.cmd` once ffprobe.exe (and optionally ffmpeg.exe) is provided in vendor/.
