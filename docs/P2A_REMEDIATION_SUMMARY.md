# P2A Performance, Scale, and Data-Bound Remediation

This batch addresses only the P2A scope from `CODEX_INITIAL_AUDIT.md`: exact release-group filtering, scan efficiency and synthetic scale budgets, bounded IMDb imports, and bounded `raw_probe` persistence. Existing P0 and P1 protections remain in place. Windows packaging, version metadata, supply-chain work, server hardening, diagnostics hardening, and live-server E2E are outside this change.

## Exact release-group filtering

- `/api/movies` now accepts a distinct `release_group` parameter. The backend uses a parameterized, case-insensitive equality predicate; it does not reuse the broad `q` search.
- Collection navigation sends `release_group`, while the normal search box continues to send `q`.
- Exact `YTS` does not match `YTSMX`, `MYTS`, or `YTS-OTHER`; exact `QXR` does not match `QXR-Group`.
- Collection aggregation and sidebar group totals use the same case-insensitive SQLite identity as the exact filter. Case-only variants such as `YTS` and `yts` form one collection whose count equals the exact-filter total.
- The collection label uses the binary minimum spelling within each case-insensitive group, producing a deterministic display value independent of row/query order.
- Empty release-group input means no exact-group constraint. A literal `Unknown` value remains independently selectable, while blank groups remain excluded from the group collection list.
- Resolution, year, and same-row subtitle filters continue to compose with the exact group predicate.

## Scan efficiency and correctness

- Each root walk builds one per-folder snapshot containing media, subtitle, and recognized poster entries. Subtitle association, folder movie counts, and local `poster.jpg` lookup reuse that snapshot instead of enumerating the same directory for every movie.
- Scan settings are loaded once per scan. The cached external-subtitle default is passed into detection instead of rereading SQLite per movie.
- Existing movie rows for a root are loaded once by relative path. This removes a read connection/query per file; unchanged-row metadata writes are also combined into one update.
- Unchanged files continue to avoid FFprobe and sampled/full hashing when their stored size and mtime match and a full digest already exists. Older rows without the additive full digest are still safely backfilled.
- Per-file write boundaries, failure isolation, per-movie locking/current-row rereads, full-content relink verification, and per-file cancellation checks remain intact. The scan does not use one giant transaction.
- Persisted probe data is normalized even on the unchanged path, so older unbounded snapshots shrink during normal rescans without re-probing media.
- Cached external-subtitle paths are revalidated as non-symlink regular files during detection and again immediately at database reconciliation. A path removed or replaced after enumeration cannot leave stale subtitle metadata.
- Cached local-poster paths are opened with no-follow semantics where the platform provides them, then the opened descriptor and current path identities are compared before image decoding. Missing, replaced, non-regular, and symlink candidates are rejected without a second folder enumeration.

The full regression suite continues to exercise disappearing/inaccessible files, partial-scan missing/offline behavior, manual edits racing a scan, full-digest collision rejection, cancellation, immutable `original_filename`, and P0/P1 restore/concurrency behavior. The dedicated P2A module additionally proves that the folder cache preserves external subtitle and local-poster detection without any per-movie `iterdir()` fallback.

## Reproducible synthetic scale benchmark

`tests/p2a_benchmark.py` creates a temporary SQLite catalog with synthetic metadata and a representative flat-folder filesystem view. It creates no large media payloads. The unchanged scan has matching size/mtime/full-digest metadata, so expensive hashing and probing are neither needed nor performed. List, exact combined filter, and stats values are medians of three calls; startup and scan are single measured operations.

Reference run: Linux 6.18.44 x86_64, Python 3.12.14, local temporary storage, 2026-10-05.

| Catalog size | Startup | List | Exact combined filter | Stats | Unchanged scan |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.001695 s | 0.001071 s | 0.001127 s | 0.000680 s | 0.370631 s |
| 10,000 | 0.005498 s | 0.002203 s | 0.001895 s | 0.003383 s | 4.054606 s |

Regression budgets deliberately include broad CI/dev-machine margin rather than asserting microsecond behavior:

| Catalog size | Startup/list/filter/stats maximum | Unchanged scan maximum |
|---:|---:|---:|
| 1,000 | 0.5 s each | 3.0 s |
| 10,000 | 1.0 s each | 20.0 s |

These are synthetic Linux regression gates. They do not claim equivalent Windows, network-share, spinning-disk, antivirus, real-media, FFprobe, or packaged-application performance.

## Bounded IMDb import

Both title and ratings paths enforce independent bounds while retaining P1B cancellation and atomic live replacement:

| Resource | `title.basics` | `title.ratings` |
|---|---:|---:|
| Compressed/manual or downloaded input | 2 GiB | 1 GiB |
| Decompressed bytes | 12 GiB | 4 GiB |
| Input rows | 50,000,000 | 30,000,000 |
| One decompressed line | 1 MiB | 256 KiB |
| Staging SQLite allocation | 16 GiB | 8 GiB |

- Title fields are individually bounded, including 1,000-byte title/genre limits; ratings fields are limited to 32 bytes. Invalid title identifiers are not admitted to staging.
- Gzip input is consumed through bounded binary `readline()` calls, preventing one malicious line from being materialized without a limit. Total decompressed bytes count all input, including rejected/non-movie rows.
- Staging allocation is checked after each batch and final partial batch.
- Any bound failure raises `ValidationError`, removes the private staging database, and leaves live title/rating indexes, timestamps, and movie ratings unchanged. Existing cancellation checks remain active during download, bounded parsing, staging, and immediately before atomic commit.
- Limits have large headroom over the current official datasets so ordinary dataset growth does not sit near the rejection boundary.

## Bounded `raw_probe` persistence

- `raw_probe` is always valid compact JSON with a hard 128 KiB UTF-8 cap and a maximum of 256 considered streams.
- The snapshot keeps MovieVault-relevant format and stream fields: codecs, bitrates, resolution, channels/layout, frame rates, HDR color-transfer data, subtitle index/language/title, duration, and container essentials.
- Arbitrary nested payloads, format tags, comments, attachments, and unrelated tool/provider fields are discarded. Individual string values are bounded.
- If the normal safe snapshot is still too large, it is deterministically reduced to essential stream fields and then to a bounded stream prefix; JSON is re-encoded after every reduction and is never byte-truncated.

## Verification

- Dedicated P2A regression and benchmark tests: **10/10 passed in 4.918 seconds** with `ResourceWarning` promoted to an error.
- Full unit/integration suite: **97/97 passed in 11.584 seconds**.
- Strict full suite: **97/97 passed in 12.000 seconds** with `ResourceWarning` promoted to an error.
- Python compilation and JavaScript syntax check: **PASSED**.
- `qa_runner.py`: **PASS** for 97 tests, Python compilation, and Playwright visual smoke.
- Standalone synthetic 1,000- and 10,000-movie benchmarks: **PASSED** within the documented budgets.
- Oversized IMDb and adversarial probe tests: **PASSED** for compressed size, decompressed size, row count, line size, field size, staging allocation, live-index preservation, stage cleanup, valid bounded JSON, and preservation of technical/subtitle metadata.
- Review follow-up fault injection: **PASSED** for case-folded collection totals, cached subtitle disappearance, cached poster disappearance, poster-to-symlink replacement, and continued one-pass folder enumeration.

No Windows, WebView2, DPAPI, packaged executable, installer, VLC/mpv, real-library scale, or live-provider verification was performed in this batch.
