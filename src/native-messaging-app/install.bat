@echo off
:: Install the expose_home_folder_host native messaging host for Thunderbird on Windows.
:: Copies runtime files into %APPDATA% so the source folder can be deleted afterwards.

setlocal

set "INSTALL_DIR=%APPDATA%\Mozilla\NativeMessagingHosts\expose_home_folder_host_helper"
set "PY_SRC=%~dp0expose_home_folder_host.py"
set "MANIFEST_SRC=%~dp0expose_home_folder_host.json"
set "PY_DEST=%INSTALL_DIR%\expose_home_folder_host.py"
set "WRAPPER=%INSTALL_DIR%\expose_home_folder_host_runner.bat"
set "MANIFEST_DEST=%INSTALL_DIR%\expose_home_folder_host.json"
set "REG_KEY=HKCU\SOFTWARE\Mozilla\NativeMessagingHosts\expose_home_folder_host"
set "STORE_URL=ms-windows-store://pdp/?productid=9NQ7512CXL7T"

:: Detect Python 3. The Microsoft Store stub at WindowsApps\python.exe responds with
:: a non-zero exit code, so a real interpreter check is what we want here.
set "PYTHON_PRESENT=0"
python -c "import sys; sys.exit(0)" >nul 2>&1
if not errorlevel 1 set "PYTHON_PRESENT=1"

echo.
echo This will install the file system access helper app for the Thunderbird
echo add-on "VFS-Provider: Local Home Folder Access".
echo.
echo The following will happen:
if "%PYTHON_PRESENT%"=="1" echo   - Python 3: already installed, no action needed
if "%PYTHON_PRESENT%"=="0" echo   - Install Python 3 via the Microsoft Store
echo   - Copy the file system access helper app into:
echo       %INSTALL_DIR%
echo   - Register the file system access helper app under:
echo       %REG_KEY%
echo.
choice /c yn /n /m "Proceed with installation? [y/n] "
if errorlevel 2 (
  echo Installation cancelled.
  echo.
  pause
  endlocal
  exit /b 1
)
echo.

if "%PYTHON_PRESENT%"=="1" goto :do_install

echo Python 3 is required to run the helper app to orchestrate the file system
echo access. The Microsoft Store will be opened to first install the
echo "Python Install Manager". After the Store install has completed:
echo   1. Open the Python Install Manager. The "Install" button should have become
echo      an "Open" button.
echo   2. The Install Manager will install the Python interpreter and keep it
echo      up to date. All prompts during the setup process can be answered with
echo      the default choice (just press Enter).
echo.
choice /c yn /n /m "Open the Microsoft Store to install Python 3 now? [y/n] "
if errorlevel 2 goto :skip_python

echo.
echo Opening Microsoft Store...
start "" "%STORE_URL%"
echo.
echo Once Python has been installed via the Python Install Manager,
echo press any key here to continue with the installation of the file system
echo access helper app.
pause
echo.
python -c "import sys; sys.exit(0)" >nul 2>&1
if errorlevel 1 goto :skip_python

echo Python 3 detected.
echo.
goto :do_install

:skip_python
echo.
echo Skipping Python installation.
echo Please ensure a working Python environment, otherwise the file system access
echo helper app will not work.
echo.

:do_install
:: Create the install dir and copy the Python script
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
copy /y "%PY_SRC%" "%PY_DEST%" >nul

:: Create a .bat wrapper so Thunderbird can launch the Python script as an executable
(
  echo @echo off
  echo python "%PY_DEST%" %%*
) > "%WRAPPER%"

:: Write manifest with the wrapper path substituted in
powershell -NoProfile -Command ^
  "(Get-Content '%MANIFEST_SRC%') -replace '/path/to/native-messaging-app/expose_home_folder_host.py', ('%WRAPPER%' -replace '\\', '\\\\') | Set-Content '%MANIFEST_DEST%'"

:: Register the manifest path in the Windows registry
reg add "%REG_KEY%" /ve /t REG_SZ /d "%MANIFEST_DEST%" /f >nul

echo Installed to:  %INSTALL_DIR%
echo Registry key: %REG_KEY%
echo.
echo Restart Thunderbird to apply the changes.
echo The downloaded files can now be safely removed.
echo.
pause

endlocal
