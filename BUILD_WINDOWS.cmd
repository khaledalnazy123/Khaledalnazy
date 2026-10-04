@echo off
REM Developer packaging shortcut only. The installed MovieVault application NEVER opens a console window.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
if errorlevel 1 (
  echo.
  echo Build failed. Review the message above, then press any key.
  pause >nul
)
