@echo off
REM Double-click this to start CableLIMS. Leave the black window open while
REM using the app -- closing it stops the server. Minimize it instead.
cd /d "%~dp0backend"
if not exist venv\Scripts\python.exe (
    echo.
    echo First-time setup has not been run yet.
    echo Double-click first_time_setup.bat first, then come back to this.
    echo.
    pause
    exit /b 1
)
echo Starting CableLIMS...
echo Once you see "Application startup complete", open this PC's browser to:
echo     http://localhost:8000
echo For phones on the same Wi-Fi, use this PC's network address instead of "localhost" --
echo run ipconfig in a separate window to find it, e.g. http://192.168.1.50:8000
echo.
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
