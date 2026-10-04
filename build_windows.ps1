# Execute this in Windows PowerShell or PowerShell 7 from the extracted source folder.
# Needs Python 3.12 x64, Inno Setup 6 and ffprobe.exe from a trusted FFmpeg distribution.
param([switch]$PortableOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'MovieVault v2 Windows Release Builder' -ForegroundColor Cyan
$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python Launcher (py.exe) missing. Install Python 3.12 x64 with pip first.' }
& py -3.12 -c "import sys; assert sys.maxsize > 2**32; print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 (64-bit) and retry.' }
if (-not (Test-Path 'vendor\ffprobe.exe')) {
  $probe = Get-Command ffprobe.exe -ErrorAction SilentlyContinue
  if ($probe) { Copy-Item $probe.Source 'vendor\ffprobe.exe' }
}
if (-not (Test-Path 'vendor\ffprobe.exe')) {
  throw 'Required: put ffprobe.exe in vendor\ffprobe.exe (from your trusted FFmpeg Windows distribution, with its applicable license). This build intentionally refuses to ship missing video-analysis capability.'
}
if (-not (Test-Path 'vendor\ffmpeg.exe')) {
  $encoder = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
  if ($encoder) { Copy-Item $encoder.Source 'vendor\ffmpeg.exe' }
}
if (-not (Test-Path 'vendor\ffmpeg.exe')) { Write-Warning 'ffmpeg.exe not bundled. Generate Custom Poster will require FFmpeg on PATH.' }
& py -3.12 -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& py -3.12 -m pip install -r requirements-windows.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& py -3.12 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed; package will not be built.' }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }
$ffmpegBundle = @()
if (Test-Path 'vendor\ffmpeg.exe') { $ffmpegBundle = @('--add-binary', 'vendor\ffmpeg.exe;vendor') }
& py -3.12 -m PyInstaller --noconfirm --clean --windowed --onedir --name MovieVault --icon assets\movievault.ico --add-data 'web;web' --add-binary 'vendor\ffprobe.exe;vendor' $ffmpegBundle --collect-all webview --collect-all clr_loader --collect-all pythonnet MovieVault.pyw
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
if (-not (Test-Path 'dist\MovieVault\MovieVault.exe')) { throw 'Executable was not produced.' }
New-Item -ItemType Directory -Force release | Out-Null
Compress-Archive -Path dist\MovieVault\* -DestinationPath release\MovieVaultV2_Portable_RC1.zip -Force
Write-Host 'Portable package created.' -ForegroundColor Green
if ($PortableOnly) { exit 0 }
$inno = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $inno) { throw 'Inno Setup 6 not found. Portable ZIP was built, but Setup.exe needs Inno Setup 6.' }
& $inno 'MovieVault.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
Write-Host 'Setup created at release\MovieVault_Setup_v2.0.0_RC1.exe' -ForegroundColor Green
