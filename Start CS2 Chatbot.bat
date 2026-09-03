@echo off
REM Double-click launcher. First run sets everything up, later runs start in a couple of seconds.
title CS2 Chatbot
cd /d "%~dp0"

echo.
echo   CS2 Chatbot
echo   ===========
echo.

REM py.exe ships with the python.org installer and is the most reliable way to find Python.
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY python --version >nul 2>&1 && set PY=python

if not defined PY (
  echo   Python is not installed.
  echo.
  echo   1. A download page will open in a moment.
  echo   2. Download Python for Windows and run the installer.
  echo   3. IMPORTANT: tick "Add python.exe to PATH" on the first screen.
  echo   4. When it finishes, double-click this file again.
  echo.
  pause
  start "" https://www.python.org/downloads/windows/
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo   First run: setting up. This takes a few minutes, and only happens once.
  echo.
  %PY% -m venv .venv
  if errorlevel 1 goto failed
  ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
  ".venv\Scripts\python.exe" -m pip install -e . --quiet
  if errorlevel 1 goto failed
  echo   Setup finished.
  echo.
)

echo   Starting. Your browser will open the control panel.
echo   Keep this window open while you play; closing it stops the bot.
echo.
".venv\Scripts\python.exe" -m cs2bot
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo   Something went wrong. Copy the message above when asking for help.
echo.
pause
exit /b 1
