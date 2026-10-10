@echo off
rem Builds TurtleBotConnect.exe from TurtleBotConnect.cs with the C# compiler that ships with
rem Windows (.NET Framework 4.x). No downloads, no Visual Studio needed.
rem Then writes the SHA-256 of the new exe to TurtleBotConnect.exe.sha256.
rem Usage: double-click it, or run  build.cmd  from a terminal (add /nopause to never pause).
setlocal EnableExtensions
cd /d "%~dp0"

set "PAUSE_AT_END=0"
rem Pause only when started by double-click (Explorer runs: cmd /c ""<full path of this file>" "),
rem so the window stays open long enough to read the result.
if /i "%~1"=="/nopause" goto :pausechecked
echo "%cmdcmdline%" | find /i "%~f0" >nul 2>&1 && set "PAUSE_AT_END=1"
:pausechecked

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo ERROR: the .NET Framework 4 C# compiler was not found:
  echo   %WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
  echo Windows 10 and 11 include it. Turn on ".NET Framework 4.8 Advanced Services" in
  echo "Turn Windows features on or off" and run this again.
  set "RC=1"
  goto :end
)

echo Compiling TurtleBotConnect.cs with
echo   %CSC%
"%CSC%" /nologo /optimize+ /target:exe /platform:anycpu /out:TurtleBotConnect.exe TurtleBotConnect.cs
if errorlevel 1 (
  echo ERROR: compilation failed. See the messages above.
  set "RC=1"
  goto :end
)

set "HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile TurtleBotConnect.exe SHA256') do (
  if not defined HASH set "HASH=%%H"
)
if not defined HASH (
  echo ERROR: certutil could not hash TurtleBotConnect.exe.
  set "RC=1"
  goto :end
)
rem Older Windows versions print the hash with spaces between the bytes; remove them.
set "HASH=%HASH: =%"
> TurtleBotConnect.exe.sha256 echo %HASH%

echo.
echo Built   %~dp0TurtleBotConnect.exe
echo SHA-256 %HASH%
echo (also written to TurtleBotConnect.exe.sha256)
set "RC=0"

:end
if "%PAUSE_AT_END%"=="1" pause
exit /b %RC%
