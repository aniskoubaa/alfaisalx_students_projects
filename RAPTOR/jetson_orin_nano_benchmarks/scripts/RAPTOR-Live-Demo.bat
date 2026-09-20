@echo off
setlocal
title RAPTOR - live perception demo

REM Runs the deployed tier 1+2 model on the Jetson's live camera and streams the
REM results here. Video frames stay on the Jetson (the window needs a local
REM display); this shows the detections, posture and timings as text.
REM
REM For the actual video window: log in on the Jetson's monitor and double-click
REM "RAPTOR Live Demo" on its desktop.

set JETSON=alfaisal-x-nx@100.100.100.1
set KEY=%USERPROFILE%\.ssh\claude_nx
set VENV=/home/alfaisal-x-nx/raptor-venv/bin/python
set DEMO=/home/alfaisal-x-nx/raptor-bench-scripts/raptor_live_demo.py

echo  ____      _    ____ _____ ___  ____
echo ^|  _ \    / \  ^|  _ \_   _/ _ \^|  _ \    live perception
echo ^| ^|_) ^|  / _ \ ^| ^|_) ^|^| ^|^| ^| ^| ^| ^|_) ^|   detect + pose + posture
echo ^|  _ ^<  / ___ \^|  __/ ^| ^|^| ^|_^| ^|  _ ^<
echo ^|_^| \_\/_/   \_\_^|    ^|_^| \___/^|_^| \_\
echo.

if not exist "%KEY%" (
    echo ERROR: SSH key not found at %KEY%
    echo   Without it this machine cannot reach the Jetson.
    goto :hold
)

echo Checking the Jetson is reachable...
ssh -i "%KEY%" -o BatchMode=yes -o ConnectTimeout=8 %JETSON% "echo ok" >nul 2>&1
if errorlevel 1 (
    echo ERROR: cannot reach the Jetson at 100.100.100.1
    echo.
    echo   Check the Ethernet cable and that the board is powered on.
    echo   NOTE: 100.100.100.x overlaps your ISP's carrier-grade NAT range, so a
    echo   ping can "succeed" against an unrelated internet host when the cable
    echo   is out. Trust this SSH check, not ping.
    goto :hold
)
echo   reachable.
echo.

echo Checking the camera...
ssh -i "%KEY%" -o BatchMode=yes %JETSON% "test -e /dev/video0" >nul 2>&1
if errorlevel 1 (
    echo ERROR: no camera at /dev/video0 on the Jetson.
    echo   Plug it in ^(prefer a USB 3.0 port^) and try again.
    goto :hold
)
echo   camera present.
echo.
echo Starting. TensorRT takes a few seconds to load the engine.
echo Press Ctrl+C to stop.
echo ---------------------------------------------------------------
echo.

ssh -i "%KEY%" -o BatchMode=yes -t %JETSON% "%VENV% %DEMO% --no-display"

echo.
echo ---------------------------------------------------------------
echo Demo stopped.

:hold
echo.
pause
endlocal
