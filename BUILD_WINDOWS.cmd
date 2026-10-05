@echo off
REM Developer packaging shortcut only. The installed MovieVault application NEVER opens a console window.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
set "BUILD_EXIT=%ERRORLEVEL%"
if not "%BUILD_EXIT%"=="0" (
  echo.
  echo Build failed. Review the message above, then press any key.
  if not defined CI pause >nul
  exit /b %BUILD_EXIT%
)
echo Build completed successfully.
exit /b 0
