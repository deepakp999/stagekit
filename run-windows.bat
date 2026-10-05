@echo off
REM StageKit - run locally on Windows for testing. Double-click or run .\run-windows.bat
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

REM Prefer uv: it fetches its own Python 3.12 for this project and installs packages fast.
where uv >nul 2>nul
if errorlevel 1 goto :nouv

if not exist .venv (
  echo Creating Python 3.12 environment with uv...
  uv python install 3.12
  uv venv --python 3.12 .venv
  if errorlevel 1 goto :fail
)
if not exist .venv\installed.flag (
  echo Installing packages with uv - first time only...
  uv pip install --python .venv torch --index-url https://download.pytorch.org/whl/cpu
  if errorlevel 1 goto :fail
  uv pip install --python .venv -r requirements.txt
  if errorlevel 1 goto :fail
  echo ok> .venv\installed.flag
)
goto :run

:nouv
if not exist .venv (
  echo Creating Python environment...
  py -3.12 -m venv .venv 2>nul || py -3.11 -m venv .venv 2>nul
  if not exist .venv (
    echo Python 3.12 not found. Easiest fix - install uv, then run this again:
    echo     winget install astral-sh.uv
    pause
    exit /b 1
  )
)
if not exist .venv\installed.flag (
  echo Installing packages - first time only, about 5-10 minutes...
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
  if errorlevel 1 goto :fail
  .venv\Scripts\python -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  echo ok> .venv\installed.flag
)

:run
if not exist data mkdir data
echo.
echo StageKit is starting at http://localhost:8080   (login: %APP_USER% / %APP_PASSWORD%)
echo Keep this window open while testing.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8080"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
pause
exit /b 0

:fail
echo.
echo Setup failed - see the messages above. Delete the .venv folder before trying again.
pause
exit /b 1
