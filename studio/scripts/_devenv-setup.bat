@echo off
rem Build the Windows installer (Inno Setup, bundled via the `innosetup` npm pkg).
rem %~1 = fork dir. Needs VSCode-win32-x64\ next to it (the compiled app).
set "PATH=C:\Program Files (x86)\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set "VSCODE_SKIP_NODE_VERSION_CHECK=1"
cd /d "%~1"
call npm run gulp -- vscode-win32-x64-inno-updater
if errorlevel 1 exit /b 1
call npm run gulp -- vscode-win32-x64-user-setup
