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
echo.
echo B4 (Review #2 remediation): this only listens on the server itself now
echo (127.0.0.1) -- phones and other PCs reach the app through Caddy's HTTPS
echo proxy instead (see DEPLOYMENT.md step 7), not this port directly.
echo --proxy-headers/--forwarded-allow-ips lets the app see each device's
echo real IP address (for login lockout and the audit log) even though every
echo request now arrives via Caddy's own loopback connection -- without it,
echo every device would look like it's the same machine.
echo.
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
pause
