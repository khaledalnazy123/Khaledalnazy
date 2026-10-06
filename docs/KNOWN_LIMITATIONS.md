# Known limitations — MovieVault source release candidate

- Windows installer has not been compiled or executed in this Linux build environment. Windows UI integration and DPAPI require real testing on the user's device.
- Authenticode support is implemented, but this repository contains no signing certificate or private key. A build without external signing configuration is explicitly marked `UNSIGNED`, never presented as signed.
- The `v1 → v2` importer is intentionally one-way, explicit, preview-first, and allows only a new/empty v2 catalog. It does not merge two nonempty catalogs.
- v1 external-source paths must still exist on the user's machine for playing/scanning; importing the database does not copy multi-GB movies.
- IMDb official datasets carry source usage terms. Titles are text metadata, not an image library. IMDb rating values appear after importing official ratings dataset.
- TMDb official images use a temporary cache/expiration and provider attribution; no permanent copy of TMDb API content is promised.
- Gemini identification is an opt-in suggestion verified independently; cannot promise perfect results or that a Gemini Pro consumer plan includes API quota.
- VLC/mpv is needed to reliably pass a specifically selected external subtitle without rewriting originals.
- Multiple Editions merging, an independent Duplicate Detector screen, and detailed Recently Watched remain planned instead of falsely marked complete.
- Screenshot generator depends on ffmpeg.exe available in vendor or PATH; if unavailable it reports a clear error.
- Only synthetic/fictional test assets have been used during current automated regression tests; no real user's movie collection or tokens were included.
