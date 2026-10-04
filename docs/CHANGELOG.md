# Changelog

## 2.0.0-rc.1 — source release candidate
- Separate v2 profile and opt-in import from v1 app/data folder, SQLite or backup ZIP; preview counts, snapshot and no credential carry-over.
- Fixed staging checkpoint issue uncovered in regression QA: the migrated SQLite file must not depend on WAL sidecars after activation.
- Preserves the pywebview private `_window` binding that fixed the prior desktop freeze.
- UI card improvements, optional compound filters, Copy Name, subtitle sources, Arabic unknown-language default and per-subtitle Apply Changes.
- Preferred external subtitle playback via VLC/mpv without renaming original files.
- IMDb official rating import, TMDb cast/metadata, opt-in Gemini suggestion independently checked against TMDb.
- Local generated poster option via FFmpeg, managed online poster fallbacks.
- Theme selector, Favorites, Personal Rating, Smart Update All modes, Cancel Job, privacy-minimized diagnostic ZIP.
- Replaced external TMDb logo fetch in Settings with a local UI mark to avoid delaying offline UI load; official attribution remains linked.
- Windows installer script uses distinct v2 AppId and install path so v1 remains side by side.
