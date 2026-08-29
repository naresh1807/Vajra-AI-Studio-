<#
  Sets up the Vajra AI Studio fork: clones Code-OSS at a pinned tag, rebrands
  product.json, and bundles the Vajra extension as a built-in. Run build.ps1
  afterwards to compile the app.

  Prereqs (one-time, admin): git, Node 24.x, Python 3.12, VS Build Tools with the
  "Desktop development with C++" workload + Windows 11 SDK. The Spectre-mitigated
  MSVC libs are NOT required - this script drops that requirement via
  Directory.Build.targets.

  The fork is cloned OUTSIDE this repo, at a path WITHOUT SPACES (-BuildDir),
  because VS Code's own build scripts break on spaces in the checkout path.
  Default: C:\vajra-studio-build. ~10 GB disk, first `npm ci` ~15-20 min.

  Usage:  scripts\bootstrap.ps1 [-Tag 1.135.0] [-Marketplace openvsx|ms] [-BuildDir C:\vajra-studio-build]
#>
param(
  [string]$Tag = "1.135.0",
  [ValidateSet("openvsx", "ms")][string]$Marketplace = "openvsx",
  [string]$BuildDir = "C:\vajra-studio-build"
)

$ErrorActionPreference = "Stop"
$studio = Split-Path $PSScriptRoot -Parent
$repo   = Split-Path $studio -Parent
if ($BuildDir -match '\s') { throw "BuildDir must not contain spaces (VS Code's build breaks): '$BuildDir'" }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
$vscode = Join-Path $BuildDir "vscode"
# a stable pointer so build.ps1 finds it
Set-Content (Join-Path $studio ".builddir") $BuildDir

if (-not (Test-Path $vscode)) {
  Write-Host "Cloning microsoft/vscode @ $Tag -> $vscode ..." -ForegroundColor Cyan
  git clone --depth 1 --branch $Tag https://github.com/microsoft/vscode.git $vscode
} else {
  Write-Host "vscode exists - checking out $Tag" -ForegroundColor Cyan
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

Copy-Item (Join-Path $PSScriptRoot "Directory.Build.targets") $vscode -Force

Write-Host "Installing vscode dependencies (this is the long part) ..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "_devenv-npm-ci.bat") $vscode
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }

Write-Host "`nBootstrap done. Next:" -ForegroundColor Green
Write-Host "  scripts\build.ps1        # compile -> studio\VajraAIStudio-win32-x64\"
Write-Host "  # or for a dev run:  cd $vscode ; .\scripts\code.bat"
