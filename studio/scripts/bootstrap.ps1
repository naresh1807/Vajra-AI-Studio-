<#
  Sets up the Vajra AI Studio fork: clones Code-OSS at a pinned tag, rebrands
  product.json, and bundles the Vajra extension as a built-in. Run build.ps1
  afterwards to compile the app.

  Prereqs: git, Node 20/22, Python 3.x, and the VS C++ Build Tools (all already
  installed for this repo). ~10 GB disk, first `npm ci` ~15 min.

  Usage:  scripts\bootstrap.ps1 [-Tag 1.135.0]
#>
param([string]$Tag = "1.135.0")

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

Write-Host "Bundling the Vajra extension as a built-in ..." -ForegroundColor Cyan
Push-Location (Join-Path $repo "vscode-extension")
npm install
npm run build
Pop-Location
$dest = Join-Path $vscode "extensions\vajra"
robocopy (Join-Path $repo "vscode-extension") $dest /MIR /XD node_modules src /XF *.vsix tsconfig.json .vscodeignore | Out-Null

Write-Host "Installing vscode dependencies (this is the long part) ..." -ForegroundColor Cyan
Push-Location $vscode
npm ci
Pop-Location

Write-Host "`nBootstrap done. Next:" -ForegroundColor Green
Write-Host "  scripts\build.ps1        # compile -> ..\VajraAIStudio-win32-x64\"
Write-Host "  # or for a dev run:  cd studio\vscode ; .\scripts\code.bat"
