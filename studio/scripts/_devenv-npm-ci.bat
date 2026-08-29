@echo off
rem npm ci for the Code-OSS fork inside a working VS build environment.
rem vcvars needs vswhere on PATH; add the VS Installer dir so it resolves.
set "PATH=C:\Program Files (x86)\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined LIB (
  echo [error] vcvars64.bat did not set LIB - VS Build Tools / Windows SDK incomplete.
  exit /b 1
)
rem .nvmrc pins a Node minor we may be a couple patches behind; the build is
rem TS/gulp/electron and works fine on any Node 24.x.
set "VSCODE_SKIP_NODE_VERSION_CHECK=1"
cd /d "%~1"
call npm ci
