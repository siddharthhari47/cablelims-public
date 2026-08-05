@echo off
REM Double-click this to run CableLIMS's backend test suite -- the same
REM suite this codebase's own comments reference ("proven by the
REM golden-value test suite", login_throttle.py's reset_all() docstring,
REM etc.) so those claims are things you can actually verify yourself, not
REM just take on trust. Also what an ISO/IEC 17025 assessor would want to
REM see run, per DEPLOYMENT.md / README.md.
REM
REM Installs dev-only tooling (pytest, ruff, mypy, pip-audit -- see
REM backend\requirements-dev.txt) into the SAME venv first_time_setup.bat
REM already created; never touches backend\data (your real database).
cd /d "%~dp0backend"
if not exist venv\Scripts\python.exe (
    echo.
    echo First-time setup has not been run yet.
    echo Double-click first_time_setup.bat first, then come back to this.
    echo.
    pause
    exit /b 1
)
echo === Installing test dependencies ===
venv\Scripts\python.exe -m pip install -r requirements-dev.txt -q

echo.
echo === Running tests (this takes about a minute) ===
venv\Scripts\python.exe -m pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80

echo.
pause
