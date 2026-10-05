# Run from a source checkout on Windows. Release acceptance requires Python 3.12
# x64, a trusted ffprobe.exe, and (unless -PortableOnly) Inno Setup 6.
param([switch]$PortableOnly)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

function Assert-NativeSuccess([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE."
  }
}

function Find-SignTool {
  $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
  if (Test-Path $kits) {
    return Get-ChildItem $kits -Filter signtool.exe -File -Recurse |
      Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
      Sort-Object FullName -Descending |
      Select-Object -ExpandProperty FullName -First 1
  }
  return $null
}

function Invoke-AuthenticodeSign([string]$Path) {
  if ($script:signCertificateThumbprint) {
    $arguments = @('sign', '/sha1', $script:signCertificateThumbprint, '/fd', 'SHA256', '/tr', $script:timestampUrl, '/td', 'SHA256', $Path)
  } else {
    $arguments = @('sign', '/f', $script:signCertificatePath, '/p', $script:signCertificatePassword, '/fd', 'SHA256', '/tr', $script:timestampUrl, '/td', 'SHA256', $Path)
  }
  & $script:signTool @arguments
  Assert-NativeSuccess "Authenticode signing of $Path"
  & $script:signTool verify /pa /all $Path
  Assert-NativeSuccess "Authenticode verification of $Path"
}

try {
  Write-Host 'MovieVault Windows release builder' -ForegroundColor Cyan
  foreach ($directory in @('build', 'dist', 'release')) {
    if (Test-Path $directory) { Remove-Item -Recurse -Force $directory }
  }

  if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw 'Python Launcher (py.exe) is missing. Install Python 3.12 x64 with pip.'
  }
  & py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32; print(sys.version)"
  Assert-NativeSuccess 'Python 3.12 x64 validation'

  & py -3.12 release_tool.py validate-lock --lock requirements-build.lock --bootstrap
  Assert-NativeSuccess 'Build-tool lock validation'
  & py -3.12 release_tool.py validate-lock --lock requirements-windows.lock
  Assert-NativeSuccess 'Windows dependency lock validation'

  & py -3.12 -m pip install --require-hashes --no-deps -r requirements-build.lock
  Assert-NativeSuccess 'Hashed build-tool installation'
  & py -3.12 -m pip install --require-hashes --no-deps --no-build-isolation -r requirements-windows.lock
  Assert-NativeSuccess 'Hashed Windows dependency installation'

  & py -3.12 -m unittest discover -s tests -v
  Assert-NativeSuccess 'Automated test suite'

  New-Item -ItemType Directory -Force 'build\external', 'release' | Out-Null

  $ffprobeSource = $null
  $ffprobeOrigin = $null
  if (Test-Path 'vendor\ffprobe.exe' -PathType Leaf) {
    $ffprobeSource = (Resolve-Path 'vendor\ffprobe.exe').Path
    $ffprobeOrigin = 'repository vendor input'
  } else {
    $probe = Get-Command ffprobe.exe -ErrorAction SilentlyContinue
    if ($probe) {
      $ffprobeSource = $probe.Source
      $ffprobeOrigin = 'build host PATH input'
    }
  }
  if (-not $ffprobeSource) {
    throw 'ffprobe.exe is required. Supply a trusted copy in vendor\ or on PATH.'
  }
  Copy-Item $ffprobeSource 'build\external\ffprobe.exe'

  $ffmpegPresent = $false
  $ffmpegOrigin = 'not bundled'
  if (Test-Path 'vendor\ffmpeg.exe' -PathType Leaf) {
    Copy-Item (Resolve-Path 'vendor\ffmpeg.exe').Path 'build\external\ffmpeg.exe'
    $ffmpegPresent = $true
    $ffmpegOrigin = 'repository vendor input'
  } else {
    $encoder = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($encoder) {
      Copy-Item $encoder.Source 'build\external\ffmpeg.exe'
      $ffmpegPresent = $true
      $ffmpegOrigin = 'build host PATH input'
    }
  }
  if (-not $ffmpegPresent) {
    Write-Warning 'ffmpeg.exe is not bundled; custom-poster generation will require FFmpeg on PATH.'
  }

  $binaryArguments = @('release_tool.py', 'binary-metadata', '--output', 'build\external-binaries.json', '--ffprobe', 'build\external\ffprobe.exe', '--ffprobe-origin', $ffprobeOrigin)
  if ($ffmpegPresent) {
    $binaryArguments += @('--ffmpeg', 'build\external\ffmpeg.exe', '--ffmpeg-origin', $ffmpegOrigin)
  }
  & py -3.12 @binaryArguments
  Assert-NativeSuccess 'External binary identity and hash validation'

  $version = & py -3.12 release_tool.py version | ConvertFrom-Json
  Assert-NativeSuccess 'Authoritative version resolution'
  & py -3.12 release_tool.py pyinstaller-version --output 'build\MovieVault.version.txt'
  Assert-NativeSuccess 'Windows executable version-resource generation'

  $signCertificateThumbprint = $env:MOVIEVAULT_SIGN_CERT_THUMBPRINT
  $signCertificatePath = $env:MOVIEVAULT_SIGN_CERT_PATH
  $signCertificatePassword = $env:MOVIEVAULT_SIGN_CERT_PASSWORD
  $timestampUrl = $env:MOVIEVAULT_SIGN_TIMESTAMP_URL
  $signingRequested = [bool]$signCertificateThumbprint -or [bool]$signCertificatePath -or [bool]$signCertificatePassword -or [bool]$timestampUrl
  $signingConfigured = ([bool]$signCertificateThumbprint -and [bool]$timestampUrl) -or ([bool]$signCertificatePath -and [bool]$signCertificatePassword -and [bool]$timestampUrl)
  if ($signCertificateThumbprint -and ($signCertificatePath -or $signCertificatePassword)) {
    throw 'Choose exactly one signing identity: certificate-store thumbprint or PFX path/password.'
  }
  if ($signingRequested -and -not $signingConfigured) {
    throw 'Signing configuration is incomplete. Use a certificate thumbprint, or a PFX path plus password, and an HTTPS timestamp URL.'
  }
  if ($signingConfigured -and $timestampUrl -notmatch '^https://') {
    throw 'MOVIEVAULT_SIGN_TIMESTAMP_URL must use HTTPS.'
  }
  $signingState = 'UNSIGNED'
  $signTool = $null
  if ($signingConfigured) {
    if ($signCertificatePath -and -not (Test-Path $signCertificatePath -PathType Leaf)) {
      throw 'MOVIEVAULT_SIGN_CERT_PATH does not identify a certificate file.'
    }
    $signTool = Find-SignTool
    if (-not $signTool) { throw 'signtool.exe was not found for the requested signed build.' }
    $signingState = 'SIGNED'
  } else {
    Write-Warning 'No signing credentials were configured. Artifacts will be explicitly marked UNSIGNED.'
  }

  $ffmpegBundle = @()
  if ($ffmpegPresent) { $ffmpegBundle = @('--add-binary', 'build\external\ffmpeg.exe;vendor') }
  & py -3.12 -m PyInstaller --noconfirm --clean --windowed --onedir --contents-directory . --name MovieVault --icon assets\movievault.ico --version-file build\MovieVault.version.txt --add-data 'VERSION;.' --add-data 'web;web' --add-binary 'build\external\ffprobe.exe;vendor' @ffmpegBundle --collect-all webview --collect-all clr_loader --collect-all pythonnet MovieVault.pyw
  Assert-NativeSuccess 'PyInstaller packaging'

  $packageRoot = (Resolve-Path 'dist\MovieVault').Path
  $application = Join-Path $packageRoot 'MovieVault.exe'
  if (-not (Test-Path $application -PathType Leaf)) { throw 'MovieVault.exe was not produced.' }
  if ($signingConfigured) { Invoke-AuthenticodeSign $application }

  Copy-Item 'build\external-binaries.json' (Join-Path $packageRoot 'external-binaries.json')
  & py -3.12 release_tool.py release-metadata --output (Join-Path $packageRoot 'release-metadata.json') --binary-metadata 'build\external-binaries.json' --signing-state $signingState
  Assert-NativeSuccess 'Release metadata generation'
  & py -3.12 release_tool.py sbom --output (Join-Path $packageRoot 'MovieVault.spdx.json') --lock requirements-windows.lock --binary-metadata 'build\external-binaries.json' --signing-state $signingState
  Assert-NativeSuccess 'SPDX SBOM generation'
  & py -3.12 release_tool.py validate-sbom (Join-Path $packageRoot 'MovieVault.spdx.json')
  Assert-NativeSuccess 'SPDX SBOM validation'

  $ffmpegExpectation = if ($ffmpegPresent) { 'present' } else { 'absent' }
  $manifest = Join-Path $packageRoot 'release-manifest.json'
  & py -3.12 release_tool.py verify-package --root $packageRoot --manifest $manifest --expect-ffmpeg $ffmpegExpectation
  Assert-NativeSuccess 'Packaged-content verification'
  & py -3.12 release_tool.py validate-manifest --root $packageRoot --manifest $manifest
  Assert-NativeSuccess 'Release-manifest validation'

  foreach ($metadataFile in @('external-binaries.json', 'release-metadata.json', 'MovieVault.spdx.json', 'release-manifest.json')) {
    Copy-Item (Join-Path $packageRoot $metadataFile) (Join-Path 'release' $metadataFile)
  }
  $portablePath = Join-Path 'release' $version.portable_name
  Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $portablePath -CompressionLevel Optimal
  if (-not (Test-Path $portablePath -PathType Leaf)) { throw 'Portable ZIP was not produced.' }
  Write-Host "Portable package created: $portablePath ($signingState)" -ForegroundColor Green

  if (-not $PortableOnly) {
    $inno = @(
      "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
      "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
    if (-not $inno) { throw 'Inno Setup 6 was not found; Setup.exe is a required output for a full release build.' }
    $setupBaseName = [System.IO.Path]::GetFileNameWithoutExtension($version.setup_name)
    & $inno "/DMyAppVersion=$($version.semantic_version)" "/DMyWindowsVersion=$($version.windows_numeric_version)" "/DMySetupBaseName=$setupBaseName" 'MovieVault.iss'
    Assert-NativeSuccess 'Inno Setup compilation'
    $setupPath = Join-Path 'release' $version.setup_name
    if (-not (Test-Path $setupPath -PathType Leaf)) { throw 'Expected Setup.exe was not produced.' }
    if ($signingConfigured) { Invoke-AuthenticodeSign $setupPath }
    Write-Host "Installer created: $setupPath ($signingState)" -ForegroundColor Green
  }

  Write-Host 'All requested build, verification, and packaging steps completed successfully.' -ForegroundColor Green
  exit 0
} catch {
  $failure = $_
  if (Test-Path 'release') { Remove-Item -Recurse -Force 'release' -ErrorAction SilentlyContinue }
  Write-Error $failure -ErrorAction Continue
  exit 1
}
