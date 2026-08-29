<#
  Sets up the Vajra AI Studio fork: clones Code-OSS at a pinned tag, rebrands
  product.json, and bundles the Vajra extension as a built-in. Run build.ps1
  afterwards to compile the app.

  Prereqs (one-time, admin): git, Node LTS, Python 3.12, VS Build Tools with the
  "Desktop development with C++" workload + Windows 11 SDK. The Spectre-mitigated
  MSVC libs are NOT required - this script drops that requirement for the tiny
  native helper modules via Directory.Build.targets.
  ~10 GB disk, first `npm ci` ~15-20 min.

  Usage:  scripts\bootstrap.ps1 [-Tag 1.135.0] [-Marketplace openvsx|ms]

  -Marketplace ms  points the extension gallery at Microsoft's VS Code
  Marketplace so you can install GitHub Copilot, Claude Code, ChatGPT etc.
  (default: openvsx). Either way, `Install from VSIX...` always works.
#>
param([string]$Tag = "1.135.0", [ValidateSet("openvsx", "ms")][string]$Marketplace = "openvsx")

$ErrorActionPreference = "Stop"
$studio = Split-Path $PSScriptRoot -Parent
$repo   = Split-Path $studio -Parent
$vscode = Join-Path $studio "vscode"

if (-not (Test-Path $vscode)) {
  Write-Host "Cloning microsoft/vscode @ $Tag ..." -ForegroundColor Cyan
  git clone --depth 1 --branch $Tag https://github.com/microsoft/vscode.git $vscode
} else {
  Write-Host "vscode/ exists - fetching tag $Tag" -ForegroundColor Cyan
  git -C $vscode fetch --depth 1 origin "refs/tags/${Tag}:refs/tags/${Tag}"
  git -C $vscode checkout $Tag
}

Write-Host "Rebranding product.json ..." -ForegroundColor Cyan
node (Join-Path $PSScriptRoot "apply-overrides.mjs") $vscode
node (Join-Path $PSScriptRoot "set-marketplace.mjs") $Marketplace $vscode

Write-Host "Bundling the Vajra extension as a built-in ..." -ForegroundColor Cyan
Push-Location (Join-Path $repo "vscode-extension")
npm install
npm run build
Pop-Location
$dest = Join-Path $vscode "extensions\vajra"
robocopy (Join-Path $repo "vscode-extension") $dest /MIR /XD node_modules src /XF *.vsix tsconfig.json .vscodeignore | Out-Null

# Neutralise the per-native-module Spectre-mitigation requirement (MSB8040) so
# `npm ci` doesn't need the Spectre-mitigated MSVC libs. See the file's comment.
Copy-Item (Join-Path $PSScriptRoot "Directory.Build.targets") $vscode -Force

Write-Host "Installing vscode dependencies (this is the long part) ..." -ForegroundColor Cyan
# Run inside a VS dev environment so the linker finds delayimp.lib etc.
& (Join-Path $PSScriptRoot "_devenv-npm-ci.bat") $vscode
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }

Write-Host "`nBootstrap done. Next:" -ForegroundColor Green
Write-Host "  scripts\build.ps1        # compile -> ..\VajraAIStudio-win32-x64\"
Write-Host "  # or for a dev run:  cd studio\vscode ; .\scripts\code.bat"
