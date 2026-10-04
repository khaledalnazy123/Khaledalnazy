# MovieVault v2 RC2 Feature Ledger

## Implemented in source, tested with automated mocks and/or synthetic media
- Separate profile from v1, preview/import old v1 data folder/app folder/database/Backup ZIP, staged restart migration, legacy schema upgrade; source remains read-only
- Base library scan and FFprobe, original filename, Missing/Offline handling, backups/restores
- Source Folder compact display with tooltip, Copy Movie Name, Genre/Rating on poster cards, subtitles counts, multiple custom subtitle providers
- Optional cumulative search by title/genre/actor/year/quality/status/favorites/subtitle-language/provider/translator; subtitle criteria operate on same row
- External subtitle auto association, recognized-language exception, Arabic default for unknown external, manual Apply Changes surviving rescans
- Preferred subtitle playback Auto/Selected/Ask/None with VLC/mpv, no original filenames renamed
- IMDb local metadata and official ratings import, TMDb metadata/cast/overview/ratings in separate fields, opt-in Gemini correction with independent TMDb validation
- TMDb/Commons poster fallback, manual locked poster, separate local video-frame generated poster
- Smart Update All modes Quick/Metadata/Posters/Full, cancellation option
- Optional Dark/Light/Midnight, Favorite/Watched/Personal Rating fields, resilient nested modal close
- Private activity diagnostics (ZIP export; excludes API keys and raw personal database)

## Partially complete / additional Windows acceptance required
- Soft Light visual consistency needs real WebView2/monitor review
- Live external API, rate limits and Windows DPAPI need actual connected-user acceptance tests
- ffmpeg custom frame design: quality depends on selected source scene
- Windows installer/portable packaging scripts created, not yet built on Windows

## Deferred after RC2 stabilization
- Group multiple editions of one movie under one poster card
- Dedicated duplicate-management interface and detailed Recently Watched timeline
- Fully automated Windows desktop installer UI E2E testing on a Windows runner
