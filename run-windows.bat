@echo off
REM StageKit - run locally on Windows for testing. Double-click this file.
REM Open http://localhost:8080 in Chrome. Stop with Ctrl+C (or close the window).
cd /d "%~dp0"

REM ---- your local login (change if you like) ----
set APP_USER=deepak
set APP_PASSWORD=localtest
REM -----------------------------------------------

set DATA_DIR=%~dp0data
set COOKIE_SECURE=0
set SEPARATION_MODE=balanced

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg is missing. Install it once with:   winget install Gyan.FFmpeg
  echo then close and reopen this window.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating Python environment...
  py -3.11 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.11 or 3.12 is needed: https://www.python.org/downloads/
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat

if not exist .venv\installed.flag (
  echo Installing packages - first time only, about 5-10 minutes...
  python -m pip install --upgrade pip
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install -r requirements.txt
  if errorlevel 1 (
    echo Install failed - see the messages above.
    pause
    exit /b 1
  )
  echo ok> .venv\installed.flag
)

if not exist data mkdir data
echo.
echo StageKit is starting at http://localhost:8080   (login: %APP_USER% / %APP_PASSWORD%)
echo Keep this window open while testing.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8080"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
pause
