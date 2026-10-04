@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m pip install -r requirements-qa.txt
if errorlevel 1 goto :fail
py -3.12 -m playwright install chromium
if errorlevel 1 goto :fail
echo.
echo Optional MovieVault visual QA tools are ready.
pause
exit /b 0
:fail
echo.
echo QA tool installation failed. MovieVault itself can still run without Playwright.
pause
exit /b 1
