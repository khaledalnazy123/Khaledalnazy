# MovieVault v2.0 Stable scope lock audit

Audit date: 2026-10-06

Audited baseline: `origin/main` at `150616e654379cb4c28bf522b65991183d5ede73`

Audit branch: `audit/v2-scope-lock`

Filter-completion baseline: `origin/main` at `a7b7a5774a48516f0afadf6fbf91e151fc194f65`

Filter-completion branch: `fix/v2-filter-completion`

This is a source-and-automation audit, not a Stable-release declaration. Evidence was taken from the implementation, HTTP layer, frontend, persistence behavior, automated tests, and release scripts. Documentation and test counts were not treated as substitutes for implementation.

## A. V2.0 SOURCE BLOCKERS

None. S07-05, S07-06, S07-08, S07-10, S07-11, S07-12, and S07-17 are implemented through the catalog query, HTTP API, and Advanced Filters UI, with focused regression coverage in `tests/test_v2_filters.py` and UI contract coverage in `tests/test_v2_ui_contract.py`.

## B. WINDOWS ACCEPTANCE PENDING

The following source capabilities are implemented but still require native proof. They are not classified as missing source functionality:

- S01-08: installed upgrade persistence of the separate user-data catalog.
- S06-06 and S06-07: real VLC and mpv discovery/launch/subtitle arguments.
- S11-04: real Windows DPAPI save/read/delete for both provider credentials.
- S14-01 through S14-04: native `MovieVault.exe`, `Setup.exe`, normal installer flow, and versioned artifact production.
- S14-05 through S14-07: packaged ffprobe, optional ffmpeg, and packaged pywebview/WebView/runtime dependencies.
- S14-08 through S14-11: locked/hash-checked dependency resolution, package manifest, SPDX SBOM, and real signing path.
- S14-12 through S14-16: upgrade safety backup, data persistence/retention, v1/v2 side-by-side install, and portable ZIP on Windows.
- S15-01 through S15-25: Windows 10, Windows 11 where available, native window startup, DPI/scaling, focus, dialogs, DPAPI lifecycle, Arabic/non-ASCII paths, spaces, long paths, removable/disconnected drives, drive loss during scan, UNC paths where supported, bundled ffprobe, bundled/optional ffmpeg, VLC, mpv, TMDb, Gemini if enabled, packaged backup/restore, upgrade, uninstall retention, portable build, PyInstaller executable, Inno installer/actual Setup, signing verification, and large real-library behavior.

## C. DEFERRED v2.1

S21-01 through S21-05 remain explicitly outside the v2.0 Stable source gate: grouping editions under one card, a dedicated duplicate manager, an advanced Recently Watched timeline, arbitrary merge of two non-empty libraries, and a major architecture rewrite. No unrelated feature expansion is inferred from this audit.

## D. RELEASE DECISION

**SOURCE SCOPE COMPLETE — READY FOR WINDOWS ACCEPTANCE**

The seven filter blockers are implemented and regression-tested. S06-10 remains resolved as **NOT APPLICABLE** to an app-level embedded-track selector in v2.0: the locked scope requires embedded subtitle cataloging plus preferred playback behavior and explicit external-subtitle selection, while embedded stream choice may remain player-native. Real player behavior remains covered by the VLC/mpv Windows acceptance gate.

## Detailed requirement matrix

Test-evidence shorthand used below resolves to these concrete automated checks:

- **Catalog scan/offline/relink:** `tests/test_catalog.py::CatalogTests.test_scan_edit_rename_archive_relink_and_offline`.
- **Technical/raw probe:** `tests/test_p2a_performance.py::P2APerformanceTests.test_raw_probe_snapshot_is_valid_bounded_and_keeps_useful_metadata` plus the catalog scan test above.
- **V2 subtitle/filter features:** `tests/test_v2_features.py::V2FeatureTests.test_advanced_filter_requires_same_subtitle_row`, `test_manual_language_survives_rescan`, `test_default_unknown_external_is_arabic`, and `test_custom_sources_and_theme`.
- **Playback tests:** all four named methods in `tests/test_playback.py::PlaybackTests`, including `test_multiple_subtitles_ask_without_renaming`, `test_selected_preference_is_reversible`, `test_reject_non_member_id_missing_and_symlink`, and `test_mpv_command_is_argument_list_and_original_unmodified`.
- **TMDb/poster tests:** the eight named methods in `tests/test_tmdb.py::TMDBTests`, `tests/test_catalog.py::CatalogTests.test_manual_poster`, and the four named methods in `tests/test_online_and_safety.py::PosterAndImdb`.
- **Metadata/Gemini:** the three named methods in `tests/test_v2_metadata.py::MetadataTests` and four named methods in `tests/test_gemini_and_update.py::AiTests`.
- **Browser/visual smoke:** `tests/test_p2c_security.py::RealMovieServerBrowserTests.test_01_real_transport_happy_path_navigation_and_data`, `test_02_controlled_failures_are_safe_and_ui_recovers`, `test_03_no_page_console_or_csp_errors`, and `tests/visual_smoke.py`.
- **UI contract/static security:** the three named methods in `tests/test_v2_ui_contract.py::V2UIContract`, `tests/test_p2c_security.py::CspStaticAuditTests`, and `BackupAndArtifactTests`.
- **Restore/migration:** `tests/test_migration.py::MigrationTests`, `tests/test_p0_remediation.py::P0RemediationTests`, and the four restore-focused methods in `tests/test_p1a_integrity.py::P1ALibraryIntegrityTests`.
- **Integrity/concurrency/jobs:** the three scan/relink methods in `tests/test_p1a_integrity.py`, all 11 methods in `tests/test_p1c_concurrency.py::P1CConcurrencyTests`, and the cancellation methods in `tests/test_p1b_correctness.py::P1BCorrectnessTests`.
- **Release engineering:** all 22 named methods in `tests/test_p2b_release.py::P2BReleaseEngineeringTests`; these are static/synthetic on Linux and do not replace native artifact acceptance.
- **HTTP/Host/diagnostics:** `tests/test_server.py::HttpTests`, `tests/test_http_v2.py::V2ApiTests`, `tests/test_diagnostics.py::PrivacyTests`, `tests/test_p2c_security.py::HostAndHttpSecurityTests`, and `DiagnosticPrivacyTests`.

### SCOPE-01 — Core library

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S01-01 | Polished Windows desktop local movie library shell | PASS — IMPLEMENTED & AUTOMATED | `MovieVault.pyw`; `mv_server.run_app`; `web/index.html` | `test_desktop_bridge`; `test_p2c_security.RealMovieServerBrowserTests`; `visual_smoke.py` | Yes, covered by S15 | No | Source/UI behavior is automated; native shell remains acceptance work. |
| S01-02 | Scan one movie folder | PASS — IMPLEMENTED & AUTOMATED | `Catalog.add_root`, `Catalog.scan`, `Catalog._scan_impl` | `CatalogTests.test_scan_edit_rename_archive_relink_and_offline` | No | No | Scans regular supported media without modifying it. |
| S01-03 | Scan multiple movie folders | PASS — IMPLEMENTED & AUTOMATED | roots table and `Catalog._scan_impl(root_ids)` | `P1CConcurrencyTests.test_disable_root_reservation_rejects_scan_before_root_mutation`; catalog scan tests | Yes, removable/UNC cases | No | Root list is persistent and independently enabled/disabled. |
| S01-04 | Never permanently move/delete/rename original media during scanning | PASS — IMPLEMENTED & AUTOMATED | `_scan_impl` reads/probes only; no media mutation path | `CatalogTests.test_scan_edit_rename_archive_relink_and_offline`; `PlaybackTests.test_mpv_command_is_argument_list_and_original_unmodified` | No | No | Poster-folder output is separately opt-in and never changes media. |
| S01-05 | Display Title | PASS — IMPLEMENTED & AUTOMATED | movies schema; `Catalog.movie(s)`; card/details UI | catalog edit tests; real-server browser tests | No | No | Editable with manual-field protection. |
| S01-06 | Current Filename | PASS — IMPLEMENTED & AUTOMATED | `current_filename` schema/scan update; details UI | catalog rename/relink test | No | No | Tracks current path name. |
| S01-07 | Original Filename permanently preserved | PASS — IMPLEMENTED & AUTOMATED | `original_filename` set only on insert; details/copy UI | catalog rename/relink test; smart-update preservation test | No | No | Immutable through scans and relinks. |
| S01-08 | Local database outside application files and surviving upgrades | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `default_data_dir`; stable Inno `AppId`; `{localappdata}` install and profile separation | `V2UIContract.test_v2_installs_next_to_v1`; P2B static tests | Yes | No | Real installed upgrade/data-retention proof is pending. |

### SCOPE-02 — Technical media metadata

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S02-01 | File size | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; `movies.size_bytes`; details UI | catalog scan tests; `P2APerformanceTests.test_raw_probe_snapshot_is_valid_bounded_and_keeps_useful_metadata` | No | No | From filesystem stat. |
| S02-02 | Resolution | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; resolution fields and tags | scan/metadata tests | No | No | Verified dimensions retained separately from filename hint. |
| S02-03 | Video codec | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; `video_codec`; Full Info | metadata/scan tests | No | No | Retained and user-filterable through S07-10. |
| S02-04 | Video bitrate | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; `video_bitrate`; estimate marker | P2A raw-probe test; visual smoke | No | No | Presentation labels estimates. |
| S02-05 | Audio codec | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; `audio_codec` | metadata/scan tests | No | No | — |
| S02-06 | Audio bitrate | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; `audio_bitrate` | metadata/scan tests | No | No | — |
| S02-07 | Total/overall bitrate | PASS — IMPLEMENTED & AUTOMATED | `media_summary`; `overall_bitrate`; estimate marker | P2A raw-probe test | No | No | — |
| S02-08 | Audio channels/layout | PASS — IMPLEMENTED & AUTOMATED | `channels`, `audio_layout`; details UI | metadata/scan tests | No | No | — |
| S02-09 | FPS | PASS — IMPLEMENTED & AUTOMATED | `fps` extraction in `media_summary`; raw Full Info | P2A raw-probe test | No | No | — |
| S02-10 | HDR | PASS — IMPLEMENTED & AUTOMATED | HDR derivation and `hdr` persistence; badge | metadata/scan tests | No | No | — |
| S02-11 | Container | PASS — IMPLEMENTED & AUTOMATED | ffprobe format persisted as `container` | P2A raw-probe test | No | No | — |
| S02-12 | Video/audio/subtitle stream information | PASS — IMPLEMENTED & AUTOMATED | sanitized `raw_probe`; `detect_subtitles`; Full Info JSON | P2A raw-probe test; subtitle feature tests | No | No | Raw snapshot is size/depth bounded. |
| S02-13 | Movie source | PASS — IMPLEMENTED & AUTOMATED | filename parsing, `source`, manual edit/details | parser and catalog tests | No | No | Distinct from subtitle source. |
| S02-14 | Release/encoder group | PASS — IMPLEMENTED & AUTOMATED | filename parsing; `release_group`; collections | parser; P2A release-group regression | No | No | Case-insensitive logical grouping. |
| S02-15 | Detailed View Full Info capability | PASS — IMPLEMENTED & AUTOMATED | `web/app.js fullInfo()` and details button | real-server browser and visual smoke | No | No | Shows bounded ffprobe JSON and copy action. |
| S02-16 | Quality presentation retains bitrate, codec, encoder/group—not only size/resolution | PASS — IMPLEMENTED & AUTOMATED | details summary and technical panel show all fields | browser/visual smoke; raw-probe test | No | No | No single “quality score” substitutes for retained facts. |

### SCOPE-03 — Movie metadata

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S03-01 | Display title | PASS — IMPLEMENTED & AUTOMATED | movie schema/API/edit UI | catalog edit tests | No | No | — |
| S03-02 | Year | PASS — IMPLEMENTED & AUTOMATED | schema, parser, edit UI | parser/filter tests | No | No | Validated range. |
| S03-03 | Genre | PASS — IMPLEMENTED & AUTOMATED | `genres`, TMDb refresh, edit UI | V2 feature filter/edit tests | No | No | — |
| S03-04 | IMDb ID | PASS — IMPLEMENTED & AUTOMATED | `imdb_id`; exact matching; manual lock semantics | P1B identity/rating tests | No | No | Manual ID controls rating identity. |
| S03-05 | IMDb URL/access | PASS — IMPLEMENTED & AUTOMATED | details UI emits `imdb.com/title/<id>/` with `noopener` | visual/browser smoke | No | No | URL is derived from validated tconst. |
| S03-06 | IMDb rating | PASS — IMPLEMENTED & AUTOMATED | `imdb_ratings`; `imdb_rating`; card/details UI | `MetadataTests.test_imdb_ratings_are_real_official_file_not_tmdb_average`; P1B tests | No | No | User-accessible numeric filtering is covered by S07-05. |
| S03-07 | Cast | PASS — IMPLEMENTED & AUTOMATED | TMDb detail refresh stores `cast_names`; details UI | `MetadataTests.test_verified_tmdb_cast_is_separate_from_imdb_rating` | Yes, live TMDb | No | Provider call needs Windows acceptance. |
| S03-08 | Overview/description | PASS — IMPLEMENTED & AUTOMATED | TMDb detail refresh stores `overview`; details UI | TMDb metadata tests | Yes, live TMDb | No | — |
| S03-09 | Official IMDb offline title dataset | PASS — IMPLEMENTED & AUTOMATED | bounded `_imdb_import_impl`; settings UI/manual title file | import, cancellation, and P2A bound tests | No | No | Transactional live replacement. |
| S03-10 | Official IMDb offline rating dataset | PASS — IMPLEMENTED & AUTOMATED | bounded ratings download/import and refresh | metadata; P1B cancellation/identity; P2A bound tests | No | No | UI provides automatic official download; manual ratings-file UI is not required by locked scope. |
| S03-11 | TMDb details source | PASS — IMPLEMENTED & AUTOMATED | `TMDbClient`; `Catalog.refresh_details` | `test_tmdb`; metadata tests | Yes | No | Real credential/network behavior pending. |
| S03-12 | TMDb poster source | PASS — IMPLEMENTED & AUTOMATED | `_tmdb_poster`; provider UI | TMDb poster tests | Yes | No | Real provider acceptance pending. |
| S03-13 | Optional Gemini fallback for difficult identification | PASS — IMPLEMENTED & AUTOMATED | `mv_gemini`; `Catalog.resolve_with_gemini`; opt-in UI | `test_gemini_and_update` | Yes, if enabled | No | Detected model is adequate; manual model selection is not required. |
| S03-14 | Gemini cannot silently overwrite identity; suggestion is controlled/verified | PASS — IMPLEMENTED & AUTOMATED | suggestion table/status; independent TMDb verification before update | `test_gemini_title_is_updated_only_after_independent_verification`; wrong-ID test | No | No | Movie video is never sent. |

### SCOPE-04 — Poster management

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S04-01 | Automatic poster retrieval | PASS — IMPLEMENTED & AUTOMATED | provider selection; `_fetch_poster_impl`; post-scan queue | TMDb and Commons poster tests | Yes, live TMDb | No | Network/provider failure is isolated. |
| S04-02 | Local poster cache | PASS — IMPLEMENTED & AUTOMATED | managed `posters/<id>.jpg`; atomic `_commit_poster` | manual/TMDb/restore tests | No | No | Cache is outside movie media. |
| S04-03 | Poster source awareness | PASS — IMPLEMENTED & AUTOMATED | `poster_source`, `poster_credit`; UI | poster tests | No | No | TMDb cache policy is distinguishable. |
| S04-04 | Manual/local poster support | PASS — IMPLEMENTED & AUTOMATED | upload API; `_local_poster` snapshot candidate | manual poster and P2A candidate tests | No | No | Revalidates regular non-symlink input before use. |
| S04-05 | Manual poster locking/preservation | PASS — IMPLEMENTED & AUTOMATED | `poster_locked`; automatic commit checks | TMDb preserve-manual and P1C writer tests | No | No | Manual edit wins concurrent automation. |
| S04-06 | Optional safe `poster.jpg` inside movie folder | PASS — IMPLEMENTED & AUTOMATED | `set_poster` uses exclusive create and no-follow | dangling-symlink safety test | Yes, Windows filesystem | No | Never overwrites an existing entry. |
| S04-07 | Generated movie-frame fallback | PASS — IMPLEMENTED & AUTOMATED | `_frame_poster_impl`; labelled Custom Frame | `MetadataTests.test_user_generated_frame_poster` | Yes, bundled ffmpeg | No | Does not modify media. |
| S04-08 | No stale/wrong poster after restore | PASS — IMPLEMENTED & AUTOMATED | private candidate poster normalization and atomic generation replacement | P1A zero/manual/overlap restore tests | No | No | Omitted TMDb artwork clears references. |
| S04-09 | Automatic artwork cannot overwrite newer manual choice | PASS — IMPLEMENTED & AUTOMATED | version/policy tokens plus movie/poster locks | three P1C poster-race tests | No | No | Atomic rollback preserves prior file/row. |

### SCOPE-05 — Subtitle catalog

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S05-01 | Catalog external subtitles | PASS — IMPLEMENTED & AUTOMATED | `SUB_EXTS`; `detect_subtitles`; `_sync_subtitles` | V2 feature and playback tests | No | No | Candidate is revalidated before commit. |
| S05-02 | Catalog embedded subtitles | PASS — IMPLEMENTED & AUTOMATED | ffprobe subtitle streams become `kind='embedded'` rows | V2 feature tests | No | No | Playback selection is assessed separately. |
| S05-03 | Expected SRT/SUB/IDX/ASS/SSA/SUP/VTT and supported stream formats | PASS — IMPLEMENTED & AUTOMATED | `SUB_EXTS`; playback allowlist; ffprobe codec name | playback and subtitle tests | No | No | Also supports SMI, TTML and PGS where detected. |
| S05-04 | Subtitle language metadata | PASS — IMPLEMENTED & AUTOMATED | language inference/stream tags/edit UI | V2 manual-language tests | No | No | Manual language lock survives scan. |
| S05-05 | External/embedded kind metadata | PASS — IMPLEMENTED & AUTOMATED | subtitles `kind`; UI table | V2 feature tests | No | No | — |
| S05-06 | Subtitle source/provider metadata | PASS — IMPLEMENTED & AUTOMATED | inference, custom sources, per-row editor | V2 feature tests | No | No | Kept separate from movie source. |
| S05-07 | Subtitle translator/group metadata | PASS — IMPLEMENTED & AUTOMATED | `translator`; row editor/filter | V2 feature tests | No | No | — |
| S05-08 | Subtitle quality metadata | PASS — IMPLEMENTED & AUTOMATED | `quality`; row/default editor | manual subtitle rescan test | No | No | User-accessible same-row filtering is covered by S07-17. |
| S05-09 | Recognized Netflix/OSN/Amazon/Disney+/BluRay/WEB-DL and custom provider values | PASS — IMPLEMENTED & AUTOMATED | `DEFAULT_SUBTITLE_SOURCES`; filename inference; `add_subtitle_source` | `test_custom_sources_and_theme`; same-row filter test | No | No | Custom-source removal has backend support; removal UI is not required by scope. |
| S05-10 | Unknown external subtitle defaults to Arabic unless configured otherwise | PASS — IMPLEMENTED & AUTOMATED | `default_external_subtitle_lang`; settings UI | `test_default_unknown_external_is_arabic`; theme/settings test | No | No | Arabic/English/Unknown are exposed. |
| S05-11 | Manual subtitle metadata survives rescans | PASS — IMPLEMENTED & AUTOMATED | `_sync_subtitles` preserves manual fields | `test_manual_language_survives_rescan` | No | No | Language, source, translator and quality persist. |

### SCOPE-06 — Subtitle playback

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S06-01 | Persistent preferred subtitle behavior | PASS — IMPLEMENTED & AUTOMATED | movie preference fields; details selector; `playback_plan` | playback and V2 preference tests | No | No | Reversible. |
| S06-02 | Auto mode | PASS — IMPLEMENTED & AUTOMATED | `playback_plan` external-count policy | playback tests | No | No | One external auto-loads; multiple asks. |
| S06-03 | Ask mode | PASS — IMPLEMENTED & AUTOMATED | `SubtitleChoiceRequired`; chooser UI | `test_multiple_subtitles_ask_without_renaming` | No | No | — |
| S06-04 | None mode | PASS — IMPLEMENTED & AUTOMATED | mute-subtitle plan; mpv/VLC flags | playback tests | Yes, player execution | No | — |
| S06-05 | Selected external subtitle mode | PASS — IMPLEMENTED & AUTOMATED | membership/symlink validation; selected preference | selected/reject-member playback tests | Yes, player execution | No | — |
| S06-06 | VLC support | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `find_player`; VLC argument-list launch | playback command tests cover planning/safety | Yes | No | Needs real installed VLC verification. |
| S06-07 | mpv support | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `find_player`; mpv argument-list launch | `test_mpv_command_is_argument_list_and_original_unmodified` | Yes | No | Needs real installed mpv verification. |
| S06-08 | Launch external subtitle without permanent renaming | PASS — IMPLEMENTED & AUTOMATED | `--sub-file` argument; no rename/copy | all playback tests | No | No | Original subtitle path is passed directly. |
| S06-09 | Preserve movie/subtitle originals during playback | PASS — IMPLEMENTED & AUTOMATED | read-only plan and subprocess arguments | original-unmodified playback test | No | No | — |
| S06-10 | App-level selection of a specific embedded subtitle stream | NOT APPLICABLE | Embedded rows are cataloged; `_verified_external` intentionally limits MovieVault's explicit selection mode to external subtitle files and delegates embedded-track choice to the player | embedded catalog coverage; VLC/mpv planning tests | No | No | v2.0 locked scope does not require a MovieVault embedded-track-ID selector. Player-native embedded selection is accepted; real VLC/mpv behavior is still verified under Windows acceptance. |

### SCOPE-07 — Search and filtering

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S07-01 | User-accessible title search | PASS — IMPLEMENTED & AUTOMATED | search input; `q`; title SQL | HTTP/browser and catalog tests | No | No | Broad `q` semantics retained. |
| S07-02 | User-accessible actor filter | PASS — IMPLEMENTED & AUTOMATED | `fActor`; API parameter; cast predicate | V2 advanced-filter test | No | No | — |
| S07-03 | User-accessible genre filter | PASS — IMPLEMENTED & AUTOMATED | `fGenre`; API parameter; genre predicate | V2 advanced-filter test | No | No | — |
| S07-04 | User-accessible year filter | PASS — IMPLEMENTED & AUTOMATED | from/to controls, validated API/catalog bounds | V2 advanced-filter and P2C safe-validation tests | No | No | — |
| S07-05 | User-accessible IMDb-rating filter | PASS — IMPLEMENTED & AUTOMATED | Inclusive validated `imdb_rating_min/max` catalog/API predicates and Advanced Filters controls | `FilterCompletionTests.test_imdb_rating_min_max_range_null_and_validation`; live API composition test | No | No | Scale 0–10; NULL ratings do not match numeric ranges. |
| S07-06 | User-accessible personal-rating filter | PASS — IMPLEMENTED & AUTOMATED | Inclusive validated `personal_rating_min/max` catalog/API predicates and Advanced Filters controls | `FilterCompletionTests.test_personal_rating_min_max_range_null_and_validation`; live API composition test | No | No | Scale 0–10; unrated movies do not match numeric ranges. |
| S07-07 | User-accessible favorite filter | PASS — IMPLEMENTED & AUTOMATED | `fFavorite`; query/API/catalog predicate | V2 advanced-filter test | No | No | Supports favorites and non-favorites. |
| S07-08 | User-accessible watched filter | PASS — IMPLEMENTED & AUTOMATED | All/Watched/Unwatched selector serializes the existing `watched` API predicate and participates in Clear Filters | `FilterCompletionTests.test_watched_and_unwatched`; UI mapping/clear tests | No | No | Supports explicit watched and unwatched states. |
| S07-09 | User-accessible resolution filter | PASS — IMPLEMENTED & AUTOMATED | 4K/1080p/720p chips; `quality` mapping; persisted resolution | catalog/browser tests | No | No | Locked scope requires the concept, not every possible resolution as a separate chip. |
| S07-10 | User-accessible video-codec filter | PASS — IMPLEMENTED & AUTOMATED | Trimmed case-insensitive exact `video_codec` catalog/API predicate and Advanced Filters input | `FilterCompletionTests.test_video_codec_is_case_insensitive_and_exact`; live API composition test | No | No | Kept distinct from broad `q`. |
| S07-11 | User-accessible bitrate filter | PASS — IMPLEMENTED & AUTOMATED | Inclusive overall-bitrate min/max controls and API values in kbps, converted to stored bps | `FilterCompletionTests.test_overall_bitrate_kbps_min_max_range_null_invalid_and_estimated`; live API composition test | No | No | NULL does not match; measured and estimated stored values use identical semantics. |
| S07-12 | User-accessible movie-source filter | PASS — IMPLEMENTED & AUTOMATED | Trimmed case-insensitive exact `source` catalog/API predicate and Advanced Filters input | `FilterCompletionTests.test_movie_source_is_case_insensitive_exact_and_not_release_group`; live API composition test | No | No | Distinct from release group and subtitle source; broad `q` unchanged. |
| S07-13 | User-accessible release/encoder-group filter | PASS — IMPLEMENTED & AUTOMATED | case-insensitive `groups/stats`; exact release-group query; Collections UI | P2A exact/case/collision test | No | No | YTS/yts collapse; YTSMX and QXR-Group remain distinct. |
| S07-14 | User-accessible subtitle-language filter | PASS — IMPLEMENTED & AUTOMATED | advanced control; correlated subtitle `EXISTS` | V2 same-row filter test | No | No | — |
| S07-15 | User-accessible subtitle-source/provider filter | PASS — IMPLEMENTED & AUTOMATED | advanced source control; correlated predicate | V2 same-row filter test | No | No | — |
| S07-16 | User-accessible subtitle-translator filter | PASS — IMPLEMENTED & AUTOMATED | translator input; correlated predicate | V2 same-row filter test | No | No | — |
| S07-17 | User-accessible subtitle-translation-quality filter | PASS — IMPLEMENTED & AUTOMATED | `subtitle_quality` is included in the existing correlated subtitle `EXISTS` predicate and exposed in Advanced Filters | `FilterCompletionTests.test_subtitle_quality_uses_same_correlated_subtitle_row`; live API composition test | No | No | Language, source, translator, and quality must match one subtitle row. |
| S07-18 | User-accessible Missing filter | PASS — IMPLEMENTED & AUTOMATED | Missing chip/archive view; status predicate | catalog/browser tests | No | No | — |
| S07-19 | User-accessible Offline filter | PASS — IMPLEMENTED & AUTOMATED | Offline chip/archive view; status predicate | catalog offline test | Yes, real drive | No | — |
| S07-20 | Compound subtitle criteria apply to the same subtitle row | PASS — IMPLEMENTED & AUTOMATED | one correlated `EXISTS` containing language/source/translator/quality predicates | `V2FeatureTests.test_advanced_filter_requires_same_subtitle_row`; `FilterCompletionTests.test_subtitle_quality_uses_same_correlated_subtitle_row` | No | No | The quality filter preserves this invariant. |

### SCOPE-08 — Library integrity

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S08-01 | Available/Missing/Offline semantics | PASS — IMPLEMENTED & AUTOMATED | root reachability and scan completion updates | catalog archive/offline test | Yes, physical drive | No | Failed individual files make scan partial and retain known rows. |
| S08-02 | Disconnected drive does not mean deleted movie | PASS — IMPLEMENTED & AUTOMATED | inaccessible root marks rows `offline` | catalog offline test | Yes | No | — |
| S08-03 | Entries retained safely | PASS — IMPLEMENTED & AUTOMATED | scans update status; no automatic row deletion | catalog scan/archive test | No | No | — |
| S08-04 | Rename/move relink is conservative | PASS — IMPLEMENTED & AUTOMATED | absent-candidate plus unique full SHA-256 requirement | catalog relink and P1A collision tests | No | No | Ambiguous identities do not relink. |
| S08-05 | Sampled fingerprint alone never proves identity | PASS — IMPLEMENTED & AUTOMATED | sampled shortlist followed by `content_sha256` equality | `test_sampled_fingerprint_collision_does_not_relink_different_media` | No | No | Files are read, never renamed/modified for verification. |
| S08-06 | Manual edits persist through rescans | PASS — IMPLEMENTED & AUTOMATED | `manual_fields` locks re-read at commit | catalog/V2/P1C edit-race tests | No | No | Covers movie and subtitle edits. |
| S08-07 | One disappearing/inaccessible file does not abort wider scan | PASS — IMPLEMENTED & AUTOMATED | per-file exception handling; safe diagnostic; seen-row retention | two P1A scan-race tests | Yes, drive-loss acceptance | No | Unrelated entries are not marked missing from the transient race. |
| S08-08 | Original filename remains immutable | PASS — IMPLEMENTED & AUTOMATED | insertion-only original field | catalog rename/relink and smart-update tests | No | No | — |

### SCOPE-09 — Main UI / UX

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S09-01 | Cards show poster | PASS — IMPLEMENTED & AUTOMATED | `card()` poster endpoint/fallback | real-server browser/visual smoke | No | No | — |
| S09-02 | Cards show title | PASS — IMPLEMENTED & AUTOMATED | `card()` title markup | browser/visual smoke | No | No | — |
| S09-03 | Cards show year | PASS — IMPLEMENTED & AUTOMATED | `card()` year markup | browser/visual smoke | No | No | — |
| S09-04 | Cards show rating/key metadata | PASS — IMPLEMENTED & AUTOMATED | IMDb rating, group, genres, subtitle summary and badges | browser/visual smoke | No | No | — |
| S09-05 | Normal Details view | PASS — IMPLEMENTED & AUTOMATED | `showMovie()` | browser/visual smoke | No | No | — |
| S09-06 | View Full Info technical view | PASS — IMPLEMENTED & AUTOMATED | `fullInfo()` modal | browser/visual smoke | No | No | — |
| S09-07 | Copy Movie Name | PASS — IMPLEMENTED & AUTOMATED | card/detail copy handlers | real-server browser test | No | No | — |
| S09-08 | Copy original filename | PASS — IMPLEMENTED & AUTOMATED | `copyOriginal` details action | visual smoke/UI source audit | No | No | — |
| S09-09 | Long paths do not destroy layout | PASS — IMPLEMENTED & AUTOMATED | `.filewrap`, `.subtitle-filename`, `.root small`, modal overflow CSS | visual smoke and P2C UI static tests | Yes, real long Windows path | No | Full value remains available in details/title. |
| S09-10 | Dark, Light, and Midnight themes | PASS — IMPLEMENTED & AUTOMATED | theme selector and CSS theme rules | `test_custom_sources_and_theme`; visual smoke | No | No | Persisted in settings. |
| S09-11 | Polished desktop-library UI rather than raw admin/database UI | PASS — IMPLEMENTED & AUTOMATED | card grid, navigation, details, modals, settings | browser/visual smoke; UI contract tests | Yes, native UX | No | Subjective final polish remains part of Windows acceptance. |

### SCOPE-10 — Smart update / jobs

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S10-01 | Comprehensive Smart Update | PASS — IMPLEMENTED & AUTOMATED | `Catalog.smart_update`; UI action/mode modal | smart-update and HTTP tests | No | No | — |
| S10-02 | Scan/quick mode | PASS — IMPLEMENTED & AUTOMATED | `_smart_update_impl('quick')` | smart quick preservation test | No | No | — |
| S10-03 | Metadata mode | PASS — IMPLEMENTED & AUTOMATED | metadata refresh branch | metadata and P1C tests | No | No | — |
| S10-04 | Posters mode | PASS — IMPLEMENTED & AUTOMATED | poster fetch branch | poster/concurrency tests | No | No | — |
| S10-05 | Full mode | PASS — IMPLEMENTED & AUTOMATED | combined smart-update branch | HTTP mode validation; visual smoke | No | No | — |
| S10-06 | Background progress/status | PASS — IMPLEMENTED & AUTOMATED | job registry/API; footer progress watcher | HTTP/browser tests | No | No | — |
| S10-07 | Real safe cancellation where supported | PASS — IMPLEMENTED & AUTOMATED | cancellation checks during parse and before live commits | P1B import/download/transaction tests | No | No | Post-commit cancellation correctly reports completed. |
| S10-08 | Conflicting operations controlled | PASS — IMPLEMENTED & AUTOMATED | `job_lock`; exclusive-maintenance reservation; HTTP 409 | P1C races; P2C DELETE 409 test | No | No | Ordinary reads do not take a giant maintenance lock. |
| S10-09 | Failed/cancelled jobs release slot | PASS — IMPLEMENTED & AUTOMATED | `start_job.run()` final locked release | three P1C slot tests | No | No | Reservation failures also release in `finally`. |

### SCOPE-11 — Data and credential security

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S11-01 | SQLite/user data outside program files | PASS — IMPLEMENTED & AUTOMATED | `default_data_dir`; installer app path is separate | UI contract/P2B static tests | Yes, installed path | No | — |
| S11-02 | TMDb credentials never stored in catalog DB/backups | PASS — IMPLEMENTED & AUTOMATED | `CredentialStore`; credential file outside SQLite; backup allowlist | TMDb connect/backup tests; P0 sanitation tests | No | No | Package verifier rejects real credential filename. |
| S11-03 | Gemini credentials never stored in catalog DB/backups | PASS — IMPLEMENTED & AUTOMATED | Gemini credential store; non-Windows session-only; migration allowlists | Gemini key test; P0; P2B verifier | No | No | — |
| S11-04 | Windows persistent secrets use DPAPI | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `CryptProtectData`/`CryptUnprotectData` in credential stores | static Windows credential tests | Yes | No | Real save/read/delete must run on Windows. |
| S11-05 | Local-first architecture | PASS — IMPLEMENTED & AUTOMATED | local SQLite/server; providers are opt-in | server/browser/offline scan tests | No | No | App remains usable without provider credentials. |
| S11-06 | Movie/video files are never uploaded | PASS — IMPLEMENTED & AUTOMATED | provider payloads use title/year/IDs only; playback local | Gemini/TMDb request-mock tests | No | No | Frame generation is local. |
| S11-07 | Diagnostic export excludes secrets and raw personal DB | PASS — IMPLEMENTED & AUTOMATED | `Diagnostics.export` allowlisted metadata/logs only | diagnostics and P2C adversarial tests | No | No | User is told to review before sharing. |
| S11-08 | Loopback-only HTTP transport | PASS — IMPLEMENTED & AUTOMATED | server binds `127.0.0.1` | live-server tests | No | No | Native webview points to ephemeral loopback port. |
| S11-09 | Strict Host protection | PASS — IMPLEMENTED & AUTOMATED | pre-dispatch exact Host validation | P2C raw Host tests | No | No | Protects token-bearing bootstrap too. |
| S11-10 | Session token and Origin controls | PASS — IMPLEMENTED & AUTOMATED | token header and same-origin validation | server/P2C auth tests | No | No | Artwork endpoints also protected. |
| S11-11 | Strict CSP/security hardening | PASS — IMPLEMENTED & AUTOMATED | response headers; external JS/CSS; no inline handlers | P2C CSP/static tests and browser console test | No | No | No inline/eval escape hatch. |

### SCOPE-12 — Backup, restore, and migration

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S12-01 | Backup contains catalog DB | PASS — IMPLEMENTED & AUTOMATED | `Catalog.backup` SQLite snapshot | catalog backup/restore tests | No | No | Snapshot is integrity checked. |
| S12-02 | Backup contains allowed settings/data | PASS — IMPLEMENTED & AUTOMATED | SQLite snapshot after legacy sanitation | P0 cleanup/backup tests | No | No | Backup is explicitly disclosed as unencrypted personal data. |
| S12-03 | Backup contains eligible poster data | PASS — IMPLEMENTED & AUTOMATED | numeric managed posters except expiring TMDb cache | TMDb exclusion and P1A restore tests | No | No | Manual/local poster retained. |
| S12-04 | Backup excludes movie files | PASS — IMPLEMENTED & AUTOMATED | fixed ZIP member allowlist | catalog/P0 validation tests | No | No | — |
| S12-05 | Backup excludes provider credentials | PASS — IMPLEMENTED & AUTOMATED | credentials outside DB; settings sanitation | TMDb, Gemini, P0, P2B tests | No | No | — |
| S12-06 | Restore validates before activation | PASS — IMPLEMENTED & AUTOMATED | `validate_backup`; structural table/column/schema/integrity checks | P0 malformed/corrupt/CRC tests | No | No | Original archived DB is validated before normalization. |
| S12-07 | Restore archive processing is bounded/safe | PASS — IMPLEMENTED & AUTOMATED | member/count/size/ratio/path/symlink limits | P0 restore tests | No | No | Only manifest, DB and numeric JPEG members accepted. |
| S12-08 | Restore uses private staged candidate | PASS — IMPLEMENTED & AUTOMATED | `stage_restore`; private extraction and normalization | catalog/P0/P1A tests | No | No | Candidate is not usable before validation/upgrade/sanitation. |
| S12-09 | Restore activation is rollback/recovery-safe | PASS — IMPLEMENTED & AUTOMATED | exclusive reservation, safety snapshot, atomic replace, quarantine/rollback | P0 fault tests; P1C reservation test | No | No | Live DB/poster generation is restored together on failure. |
| S12-10 | Restore cannot retain stale poster generation | PASS — IMPLEMENTED & AUTOMATED | candidate poster normalization and whole-generation replacement | P1A overlapping-ID/zero/manual poster tests | No | No | Missing archive member never reuses old numeric poster. |
| S12-11 | Older valid backups are schema-upgraded | PASS — IMPLEMENTED & AUTOMATED | `_upgrade_catalog_schema`; meta version normalization before activation | two P1A older-schema same-instance tests | No | No | Rebackup validates and restages without restart. |
| S12-12 | Restore/migration failure does not permanently block normal startup | PASS — IMPLEMENTED & AUTOMATED | quarantine/recovery and pending validation; live rollback | P0 corruption/fault/reopen tests; migration failure tests | Yes, packaged startup | No | Startup log remains available for unrelated fatal errors. |
| S12-13 | v1→v2 migration reads/copies source without mutating v1 | PASS — IMPLEMENTED & AUTOMATED | read-only URI and SQLite backup into private stage | migration preview/activation and P0 byte-preservation tests | Yes, real v1 profile | No | — |
| S12-14 | v1 files remain unaltered | PASS — IMPLEMENTED & AUTOMATED | all mutation targets private target/stage | migration source-byte tests | Yes | No | Explicit user preview precedes staging. |
| S12-15 | Legacy credentials are not imported | PASS — IMPLEMENTED & AUTOMATED | explicit setting allowlists and repeat sanitation | three P0 credential tests | No | No | Restored v1-derived candidates are sanitized before same-instance use. |
| S12-16 | Existing populated v2 library protected from accidental overwrite | PASS — IMPLEMENTED & AUTOMATED | `_target_is_empty`; stage/apply checks | `MigrationTests.test_no_overwrite_of_populated_v2` | No | No | General non-empty merge is deferred, not silently attempted. |
| S12-17 | Migration accepts folder, database, or backup ZIP with preview | PASS — IMPLEMENTED & AUTOMATED | `resolve_legacy_source`; preview/stage API and UI | migration and HTTP tests | Yes, native pickers | No | Auto-follows real legacy user-data location when old app folder selected. |
| S12-18 | Restore/migration preserve current runtime usability rules | PASS — IMPLEMENTED & AUTOMATED | schema normalization, settings sanitation, same-instance restore reload | P0/P1A same-instance tests | No | No | No extra restart required after restore activation. |

### SCOPE-13 — Diagnostics

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S13-01 | Clear failure/error handling | PASS — IMPLEMENTED & AUTOMATED | expected 400/404/409 mapping; generic 500; UI toast handling | HTTP/P2C controlled-failure tests | No | No | Unexpected exception detail stays out of response. |
| S13-02 | Privacy-safe structured diagnostics | PASS — IMPLEMENTED & AUTOMATED | bounded JSONL `Diagnostics.event` | diagnostics/P2C adversarial tests | No | No | Field keys and values are constrained/redacted. |
| S13-03 | Export Diagnostic ZIP | PASS — IMPLEMENTED & AUTOMATED | `/api/diagnostics`; `Diagnostics.export`; settings action | HTTP/diagnostics tests | No | No | Saved locally only. |
| S13-04 | Credential/token redaction | PASS — IMPLEMENTED & AUTOMATED | `_safe` patterns and sensitive-key omission | JWT/email/API-key adversarial tests | No | No | — |
| S13-05 | Filesystem path/filename redaction | PASS — IMPLEMENTED & AUTOMATED | Windows/UNC/POSIX/media filename patterns | P2C path/filename adversarial tests | No | No | — |
| S13-06 | No raw DB in diagnostic ZIP | PASS — IMPLEMENTED & AUTOMATED | export contains summary/logs/README only | `test_export_excludes_credentials_database_and_filename` | No | No | — |
| S13-07 | Useful safe operation/failure metadata remains | PASS — IMPLEMENTED & AUTOMATED | event class, safe counts/platform/integrity | adversarial export test | No | No | Redaction does not erase event/failure class or aggregate counts. |

### SCOPE-14 — Windows build / installer source capability

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S14-01 | Produce `MovieVault.exe` | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | PyInstaller invocation and existence gate in `build_windows.ps1` | P2B static pipeline tests | Yes | No | Not built on this Linux audit host. |
| S14-02 | Produce versioned `Setup.exe` | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | Inno invocation and post-compile existence gate | P2B artifact-metadata/static tests | Yes | No | Not built on this host. |
| S14-03 | Normal Next→Next→Finish per-user installer flow | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `MovieVault.iss` modern lowest-privilege setup and postinstall launch | installer static tests | Yes | No | Needs interactive Setup acceptance. |
| S14-04 | Version consistency | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `VERSION`; `mv_version`; generated PyInstaller/Inno/artifact names | P2B version drift tests | Yes | No | Static consistency passed; native artifact properties pending. |
| S14-05 | Packaged ffprobe | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | required trusted input, copied binary, PyInstaller add-binary, provenance | P2B package/provenance tests | Yes | No | Real bundled execution pending. |
| S14-06 | Optional ffmpeg where configured | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | optional trusted input, add-binary, metadata/manifest expectation | P2B package/provenance tests | Yes | No | Absence is truthful and frame fallback explains requirement. |
| S14-07 | WebView/runtime dependencies packaged | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | PyInstaller collects webview/clr/pythonnet; verifier requires runtime support | P2B missing-runtime/package tests | Yes | No | WebView2 host/runtime startup pending. |
| S14-08 | Dependency locks/hashes | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | exact `requirements-*.lock`; `--require-hashes --no-deps` | P2B lock completeness/hash tests | Yes | No | Windows resolver/install must still run. |
| S14-09 | Package manifest | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `verify-package` emits and `validate-manifest` rechecks SHA-256 manifest | P2B manifest/tamper tests | Yes | No | Must be generated from actual package. |
| S14-10 | SPDX SBOM | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `release_tool.py sbom/validate-sbom` | P2B SPDX test | Yes | No | Must be generated/checked for actual artifact. |
| S14-11 | Signing pipeline support | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | signtool sign then verify; per-artifact truthful metadata | P2B signed/unsigned portable/full tests | Yes | No | Unsigned RC builds remain explicitly UNSIGNED. |
| S14-12 | Safe upgrade behavior | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | stable AppId and pre-install `--backup-only` abort-on-failure gate | installer/P2B static tests | Yes | No | Real upgrade/rollback behavior pending. |
| S14-13 | Persistent user DB across version updates | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | profile outside `{app}` and stable data path | UI contract/static tests | Yes | No | Real upgrade data verification pending. |
| S14-14 | Uninstall does not silently wipe personal DB | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | Inno installs only under `{app}`; catalog under user profile; no delete-data code | installer static inspection | Yes | No | Must verify with actual uninstaller. |
| S14-15 | v1/v2 side-by-side safety | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | v2-specific AppId/install/profile; opt-in migration | UI contract and migration tests | Yes | No | Real machines with v1 pending. |
| S14-16 | Portable package | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | PortableOnly mode and versioned ZIP after verification | P2B portable metadata tests | Yes | No | Native launch/package acceptance pending. |

### SCOPE-15 — Release quality / native Windows acceptance

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S15-01 | Windows 10 acceptance | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | Windows launcher/build/installer source exists | Linux/static baseline only | Yes | No | Pending real Windows 10 where available. |
| S15-02 | Windows 11 acceptance | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | Windows launcher/build/installer source exists | Linux/static baseline only | Yes | No | Pending real Windows 11. |
| S15-03 | pywebview/WebView2 startup and normal window behavior | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `mv_server.run_app`; private bridge; packaged webview | desktop bridge and browser smoke | Yes | No | Browser automation is not native WebView2 proof. |
| S15-04 | DPI/scaling | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | responsive CSS/native webview architecture | visual smoke | Yes | No | Test common Windows scaling factors. |
| S15-05 | Basic focus behavior | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | focus-visible styles, modal/navigation controls | browser smoke | Yes | No | Native keyboard/window focus pending. |
| S15-06 | Basic dialog behavior | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | modal system and native pickers/confirm flows | browser smoke and HTTP tests | Yes | No | Native picker/confirm/window modality pending. |
| S15-07 | DPAPI save/read/delete | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | both credential stores use DPAPI files and delete methods | static credential tests | Yes | No | Test both TMDb and Gemini lifecycle. |
| S15-08 | Arabic/non-ASCII paths | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `Path`, Unicode SQLite/JSON/UI use | Arabic subtitle fixtures | Yes | No | Real Windows filesystem/pickers pending. |
| S15-09 | Paths containing spaces | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | `Path`; subprocess argument lists; installer quoting | playback/build static tests | Yes | No | Real players/package pending. |
| S15-10 | Long paths where applicable | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | path-safe APIs and nonintrusive UI wrapping | CSS/browser tests | Yes | No | Windows policy/filesystem limitations must be observed. |
| S15-11 | Disconnected/removable drives | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | root-unavailable offline semantics | catalog offline tests | Yes | No | Physical media pending. |
| S15-12 | Drive loss during scan | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | per-file/root failure handling and safe statuses | deterministic P1A scan-race tests | Yes | No | Physical mid-scan removal pending. |
| S15-13 | UNC/network paths where supported | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | path model and UNC diagnostic redaction | UNC privacy tests; generic scan tests | Yes | No | Support boundary/performance must be observed on Windows. |
| S15-14 | Bundled ffprobe | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | required package binary and runtime lookup | P2B package tests | Yes | No | Execute packaged binary against real media. |
| S15-15 | Bundled/optional ffmpeg | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | optional package binary and runtime lookup | frame-poster/P2B tests | Yes | No | Verify configured package path and fallback messaging. |
| S15-16 | Real VLC playback/subtitle command | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | safe VLC argument list | playback unit tests | Yes | No | Confirm installed VLC behavior. |
| S15-17 | Real mpv playback/subtitle command | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | safe mpv argument list | playback unit tests | Yes | No | Confirm installed mpv behavior. |
| S15-18 | Real TMDb integration | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | credential/connect/match/details/poster implementation | mocked TMDb tests | Yes | No | Requires user-supplied valid credential/network. |
| S15-19 | Real Gemini integration if enabled | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | credential/connect/identify/verify implementation | mocked Gemini tests | Yes | No | Optional; test only when enabled with user credential. |
| S15-20 | Backup/restore on packaged build | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | backup/restore APIs and packaged runtime inputs | extensive catalog/P0/P1A tests | Yes | No | Test same-running-instance activation in packaged app. |
| S15-21 | Installed upgrade | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | stable AppId plus mandatory pre-upgrade backup | static installer tests | Yes | No | Test supported release-to-release path. |
| S15-22 | Uninstall data retention | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | personal data outside install tree | source inspection | Yes | No | Confirm catalog/posters/backups remain. |
| S15-23 | Portable build | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | PortableOnly packaging/metadata | P2B portable tests | Yes | No | Test extract, launch, data path, and update expectations. |
| S15-24 | PyInstaller executable, Inno installer, actual Setup.exe, and signing verification | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | mandatory build gates; per-artifact metadata; signtool verify | P2B build/signing/metadata tests | Yes | No | Run actual full build; verify signatures only when certificate is used. |
| S15-25 | Large real-library behavior | PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED | paginated SQL, indexes, folder snapshot reuse, bounded imports | deterministic 1k/10k P2A benchmarks | Yes | No | Synthetic budgets passed; a large real Windows library remains required. |

### Explicitly deferred to v2.1 / non-blockers

| ID | Requirement | Status | Source evidence | Automated-test evidence | Windows acceptance needed? | v2.0 blocker? | Notes |
|---|---|---|---|---|---|---|---|
| S21-01 | Group multiple editions under one card | DEFERRED — V2.1 | Not required by v2.0 scope | Not required | No | No | Remains deferred. |
| S21-02 | Full dedicated Duplicate Manager | DEFERRED — V2.1 | Not required by v2.0 scope | Not required | No | No | Conservative relink safety is implemented independently. |
| S21-03 | Advanced Recently Watched timeline | DEFERRED — V2.1 | Not required by v2.0 scope | Not required | No | No | Basic watched/unwatched filtering is complete at S07-08; only an advanced timeline remains deferred. |
| S21-04 | Arbitrary merge of two non-empty libraries | DEFERRED — V2.1 | Migration deliberately refuses overwrite/merge | Refusal is tested | No | No | Backup restore is replacement, not merge. |
| S21-05 | Major architecture rewrite | DEFERRED — V2.1 | Existing local-first architecture retained | Current regression suite | No | No | No rewrite is justified by this audit. |

## Audit and filter-completion validation

All commands below ran on Linux. They do not replace the native-Windows acceptance gate.

| Validation | Result |
|---|---|
| Focused filter suite: `python -m unittest -v tests.test_v2_filters` | PASS — 9 tests |
| JavaScript syntax: `node --check web/app.js` | PASS |
| Full regression suite: `python -m unittest discover -s tests -v` | PASS — 158 tests, including the 3 P2C real-server Chromium tests |
| Strict resources: `python -W error::ResourceWarning -m unittest discover -s tests -q` | PASS — 158 tests |
| `python qa_runner.py` | PASS — 158 tests, Python compilation, and visual browser smoke |

## Classification totals

The totals below are derived from the detailed matrix and must be updated together with it:

- Total atomic requirements audited: **198**
- PASS — IMPLEMENTED & AUTOMATED: **147**
- PASS — IMPLEMENTED, WINDOWS ACCEPTANCE REQUIRED: **45**
- PARTIAL — V2.0 BLOCKER: **0**
- MISSING — V2.0 BLOCKER: **0**
- REVIEW DECISION NEEDED: **0**
- DEFERRED — V2.1: **5**
- NOT APPLICABLE: **1**
