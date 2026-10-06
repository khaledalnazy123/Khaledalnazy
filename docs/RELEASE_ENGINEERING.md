# Windows release engineering

`VERSION` is the only release-version authority. Runtime/API/UI reporting, the
Windows four-part resource version, Inno Setup metadata, and portable/setup
filenames are derived from it. Release-candidate `MAJOR.MINOR.PATCH-rc.N` maps
to Windows `MAJOR.MINOR.PATCH.N`; a stable version maps to revision zero.

## Reproducible dependency inputs

The supported release target is CPython 3.12 x64 on Windows. The build validates
and installs only:

- `requirements-build.lock`: exact, hashed pip/build-backend tooling.
- `requirements-windows.lock`: exact, hashed direct and transitive runtime/build
  dependencies. Playwright is deliberately excluded because it is QA-only.

`requirements-windows.txt` is a human-readable direct-dependency policy and is
not a release-build input. The script uses `--require-hashes --no-deps`; the
second installation also uses `--no-build-isolation`, so the `proxy_tools`
source distribution cannot silently fetch an unpinned backend.

To refresh a lock, use an isolated CPython 3.12 environment, resolve the full
Windows x64 graph, review every changed package, obtain hashes from the trusted
package index, and replace the complete lock atomically. Then run:

```text
py -3.12 release_tool.py validate-lock --lock requirements-build.lock --bootstrap
py -3.12 release_tool.py validate-lock --lock requirements-windows.lock
py -3.12 -m pip download --require-hashes --no-deps --platform win_amd64 --python-version 3.12 --implementation cp --abi cp312 -r requirements-windows.lock -d <empty-review-directory>
```

Do not approve a refresh solely because installation succeeds. Review upstream
release notes, ownership, licenses, wheel/platform selection, and the recorded
hashes. Never disable TLS or hash verification to make a build pass.

## FFmpeg-family provenance

Supply a trusted `ffprobe.exe` in `vendor\` or on PATH; `ffmpeg.exe` is optional.
The build copies inputs to `build\external` and does not mutate either source.
It executes each staged binary with `-version` and records its origin category,
identity line, size, and SHA-256 in `external-binaries.json`. These records also
feed release metadata and the SPDX SBOM. The package verifier confirms bundled
binaries match their provenance hashes. Distribution remains subject to the
selected FFmpeg build's license and notices.

## Signing

No certificate, private key, or secret is stored in the repository. Signing is
enabled only with one of these external configurations plus an HTTPS timestamp:

```text
MOVIEVAULT_SIGN_CERT_THUMBPRINT + MOVIEVAULT_SIGN_TIMESTAMP_URL
MOVIEVAULT_SIGN_CERT_PATH + MOVIEVAULT_SIGN_CERT_PASSWORD + MOVIEVAULT_SIGN_TIMESTAMP_URL
```

The build calls `signtool sign` using SHA-256 and RFC 3161 timestamping, then
requires `signtool verify /pa /all` for both `MovieVault.exe` and the installer.
Partial signing configuration is a hard failure. With no configuration, the
build continues only as explicitly `UNSIGNED` in release metadata and the
manifest; it never fabricates signing success.

Signing metadata is per artifact. A portable-only build lists only the produced
`MovieVault.exe`; it never lists a Setup artifact. A full build adds the
versioned Setup filename only after Inno Setup has succeeded and the file exists.
`SIGNED` is recorded only after the corresponding `signtool verify` call returns
success. Certificate paths, thumbprints, passwords, and timestamp configuration
are never copied into release metadata.

## Build and verification outputs

Run `BUILD_WINDOWS.cmd` from CMD. It forwards options such as `-PortableOnly`
and preserves every PowerShell failure exit code. A successful full build emits:

- `MovieVault_<semantic-version>_Portable.zip`
- `MovieVault_Setup_<semantic-version>.exe`
- `MovieVault.spdx.json` (SPDX 2.3 JSON)
- `release-metadata.json`, `external-binaries.json`, and
  `release-manifest.json`

The manifest covers the complete portable runtime file set with size and
SHA-256. Verification requires the executable, UI assets, version file,
ffprobe, pywebview and Python.Runtime support, metadata, and SBOM. It rejects
symlinks, credentials, private keys, databases, backups, media/subtitles, test
trees, build inputs, and nested archives. Missing expected files or any hash
change fails the build.

Known credential rejection includes the application’s actual DPAPI filenames,
`tmdb_credential.dpapi` and `gemini_credential.dpapi`, in addition to the generic
secret/private-key/database rules. Release metadata and the manifest must carry
the same exact build mode, artifact set, presence, and per-artifact signing state.

The script treats dependency installation, tests, PyInstaller, signing,
metadata/SBOM creation, package verification, archive creation, Inno Setup, and
output existence as mandatory gates. It prints success only after all requested
gates pass.

## Acceptance boundary

Linux regression and synthetic package checks validate the release logic, not
native Windows behavior. Before publishing, execute the build and
`docs/QA_CHECKLIST_AR.md` on Windows, inspect Authenticode and SmartScreen
behavior, and validate WebView2, DPAPI, installation, upgrade, and uninstall.
