Windows build: provide trusted ffprobe.exe here (required for full technical metadata).
Optional: provide ffmpeg.exe here for Generate Custom Poster from movie frame.
Both binaries are maintained by FFmpeg, not included in source package. Observe applicable LGPL/GPL licensing, include appropriate notices/credits for distribution. Avoid unknown/untrusted binary download sources.
The build script intentionally refuses to distribute a full technical-info installer if ffprobe.exe is missing.
The release build copies inputs to a private staging directory; it never overwrites
the source-tree copies or programs found on PATH. It executes each staged binary
with -version and records that identity, origin category, size, and SHA-256 in
external-binaries.json, release metadata, and the SPDX SBOM.
