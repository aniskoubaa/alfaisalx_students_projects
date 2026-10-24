; NSIS 3 installer for TurtleBot Studio (Windows, per user: no administrator rights needed).
; Built by build.py --installer, which passes the values below with /D... options:
;   /DAPP_VERSION=1.3  /DAPP_VERSION_NUM=1.3.0.0  /DAPP_EXE=<full path of TurtleBotStudio.exe>
;   /DAPP_ICON=<full path of studio.ico>  /DOUT_DIR=<folder for the setup exe>
; By hand:  makensis /DAPP_VERSION=1.3 /DAPP_EXE=C:\path\TurtleBotStudio.exe installer.nsi
; The settings folder %APPDATA%\TurtleBotStudio (robot address, trusted robots, ssh key location) is never removed.
Unicode True

!ifndef APP_VERSION
  !error "Pass the version: makensis /DAPP_VERSION=1.3 ... (build.py reads it from version.json)"
!endif
!ifndef APP_VERSION_NUM
  !define APP_VERSION_NUM "${APP_VERSION}.0.0"
!endif
!ifndef APP_EXE
  !define APP_EXE "dist\TurtleBotStudio.exe"
!endif
!ifndef OUT_DIR
  !define OUT_DIR "dist"
!endif

!define APP_NAME "TurtleBot Studio"
!define APP_FILE "TurtleBotStudio.exe"
!define PUBLISHER "AlfaisalX Lab"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\TurtleBotStudio"
!define APP_KEY "Software\TurtleBotStudio"

Name "${APP_NAME}"
OutFile "${OUT_DIR}\TurtleBotStudio-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\TurtleBot Studio"
InstallDirRegKey HKCU "${APP_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${APP_NAME} ${APP_VERSION} - ${PUBLISHER}"

VIProductVersion "${APP_VERSION_NUM}"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} setup"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"

!include "MUI2.nsh"
!ifdef APP_ICON
  !define MUI_ICON "${APP_ICON}"
  !define MUI_UNICON "${APP_ICON}"
!endif
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_FILE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch TurtleBot Studio"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; A running program cannot be overwritten or deleted: if the file cannot be opened for writing, Studio is still open.
!macro WaitForClosed Dir Id
  _loop_${Id}:
  IfFileExists "${Dir}\${APP_FILE}" 0 _done_${Id}
  ClearErrors
  FileOpen $R0 "${Dir}\${APP_FILE}" a
  IfErrors 0 _free_${Id}
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "TurtleBot Studio is still open. Close its window (or press Quit Studio on its Tools tab), then click Retry." /SD IDCANCEL IDRETRY _loop_${Id}
  Abort
  _free_${Id}:
  FileClose $R0
  _done_${Id}:
!macroend

Section "TurtleBot Studio" SecMain
  SectionIn RO
  !insertmacro WaitForClosed "$INSTDIR" inst
  SetOutPath "$INSTDIR"
  File "/oname=${APP_FILE}" "${APP_EXE}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}.lnk" "$INSTDIR\${APP_FILE}" "" "$INSTDIR\${APP_FILE}" 0
  WriteRegStr HKCU "${APP_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_FILE}"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_FILE}" "" "$INSTDIR\${APP_FILE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "The TurtleBot Studio program and a Start menu entry."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "A shortcut on your desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  !insertmacro WaitForClosed "$INSTDIR" uninst
  Delete "$INSTDIR\${APP_FILE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\${APP_NAME}.lnk"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "${APP_KEY}"
SectionEnd

Function un.onUninstSuccess
  IfSilent +2
  MessageBox MB_OK|MB_ICONINFORMATION "TurtleBot Studio was removed.$\r$\n$\r$\nYour settings (robot address, trusted robots, key location) were kept in $APPDATA\TurtleBotStudio. Delete that folder yourself if you want them gone."
FunctionEnd
