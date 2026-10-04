@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py.exe^) was not found.
  echo Install Python 3.12 x64, then run this file again.
  pause
  exit /b 1
)
py -3.12 qa_runner.py
set ERR=%ERRORLEVEL%
echo.
if "%ERR%"=="0" (
  echo MovieVault automated QA PASSED.
) else (
  echo MovieVault automated QA FAILED. Open the newest file in qa_reports.
)
pause
exit /b %ERR%
