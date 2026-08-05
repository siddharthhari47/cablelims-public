@echo off
REM Run this ONCE, the very first time, after copying CableLIMS onto this PC.
REM Safe to run again later if something looks broken -- it won't touch any
REM samples/certificates you've already created (those live in backend\data
REM and backend\certificates, which this script never deletes).

cd /d "%~dp0backend"

echo === Step 1/3: setting up Python environment ===
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found. Install Python 3.12+ from https://www.python.org/downloads/
    echo During install, tick "Add python.exe to PATH", then run this script again.
    echo.
    pause
    exit /b 1
)

if not exist venv (
    python -m venv venv
)
venv\Scripts\python.exe -m pip install --upgrade pip -q
REM requirements.lock.txt (H13), when present, pins the FULL dependency
REM tree -- installs from it instead of requirements.txt so every install
REM gets byte-identical versions, not just of the direct dependencies but
REM everything they themselves pull in. Falls back to requirements.txt for
REM an older package that predates the lockfile.
if exist requirements.lock.txt (
    venv\Scripts\python.exe -m pip install -r requirements.lock.txt -q
) else (
    venv\Scripts\python.exe -m pip install -r requirements.txt -q
)

echo === Step 2/3: loading standard/test configuration ===
venv\Scripts\python.exe -m app.seed --config-only

echo === Step 3/3: create your login ===
echo You'll be asked for a username, name, role, and password now.
echo This is YOUR real account -- there are no default/demo passwords on this install.
venv\Scripts\python.exe -m app.create_user

echo.
echo Setup complete. Double-click start_cablelims.bat to run the app.
echo.
pause
