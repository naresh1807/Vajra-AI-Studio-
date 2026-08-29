@echo off
rem gulp build for the Code-OSS fork inside a working VS build environment.
set "PATH=C:\Program Files (x86)\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set "VSCODE_SKIP_NODE_VERSION_CHECK=1"
cd /d "%~1"
call npm run gulp -- vscode-win32-x64-min
