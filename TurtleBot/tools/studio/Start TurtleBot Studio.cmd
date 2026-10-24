@echo off
rem Double-click to start TurtleBot Studio on Windows. Needs Python 3.10 or newer (python.org).
setlocal
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo TurtleBot Studio needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then double-click this file again.
  pause
  exit /b 1
)
%PY% studio.py %*
if errorlevel 1 pause
