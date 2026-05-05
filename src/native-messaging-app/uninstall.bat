@echo off
:: Uninstall the expose_home_folder_host native messaging host for Thunderbird on Windows.

setlocal

set "INSTALL_DIR=%APPDATA%\Mozilla\NativeMessagingHosts\expose_home_folder_host_helper"
set "REG_KEY=HKCU\SOFTWARE\Mozilla\NativeMessagingHosts\expose_home_folder_host"

echo.
echo This will uninstall the file system access helper app for the Thunderbird
echo add-on "VFS-Provider: Local Home Folder Access".
echo.
echo The following will happen:
echo   - Remove the file system access helper app from:
echo       %INSTALL_DIR%
echo   - Remove the registry entry:
echo       %REG_KEY%
echo.
choice /c yn /n /m "Proceed with uninstallation? [y/n] "
if errorlevel 2 (
  echo Uninstallation cancelled.
  echo.
  pause
  endlocal
  exit /b 1
)
echo.

reg delete "%REG_KEY%" /f >nul 2>&1
if %errorlevel% equ 0 (
  echo Removed registry key: %REG_KEY%
) else (
  echo Registry key not found: %REG_KEY%
)

if exist "%INSTALL_DIR%" (
  rmdir /s /q "%INSTALL_DIR%"
  echo Removed install dir: %INSTALL_DIR%
) else (
  echo Not installed (not found): %INSTALL_DIR%
)

echo.
pause

endlocal
