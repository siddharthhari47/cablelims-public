@echo off
REM Double-click this to back up CableLIMS's data right now, or wire it into
REM Windows Task Scheduler for a nightly automatic backup (see DEPLOYMENT.md
REM section 9). Safe to run while the app is running -- it uses SQLite's
REM online backup API, which is specifically built to work against a live,
REM in-use database.
REM
REM Default destination: backend\backups\ (on this same PC/disk). That
REM protects against accidental deletion or a corrupted database, but NOT
REM against this machine's disk failing entirely. For real off-site
REM protection, pass a network drive or external disk as the first
REM argument, e.g.:
REM     backup_now.bat D:\CableLIMS-Backups
REM     backup_now.bat \\NAS\Backups\CableLIMS
cd /d "%~dp0backend"
if not exist venv\Scripts\python.exe (
    echo.
    echo First-time setup has not been run yet.
    echo Double-click first_time_setup.bat first, then come back to this.
    echo.
    pause
    exit /b 1
)
venv\Scripts\python.exe -m app.backup %1
echo.
pause
