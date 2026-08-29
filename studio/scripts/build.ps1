<#
  Compiles the Vajra AI Studio desktop app from the bootstrapped fork.
  Produces studio\VajraAIStudio-win32-x64\  (run VajraAIStudio.exe).
  ~30-45 min the first time.
#>
$ErrorActionPreference = "Stop"
$studio = Split-Path $PSScriptRoot -Parent
$vscode = Join-Path $studio "vscode"
if (-not (Test-Path (Join-Path $vscode "node_modules"))) {
  throw "Run scripts\bootstrap.ps1 first."
}
Push-Location $vscode
try {
  node (Join-Path $PSScriptRoot "apply-overrides.mjs") $vscode   # re-apply after any upstream checkout
  npm run gulp -- vscode-win32-x64-min
  $out = Join-Path (Split-Path $vscode -Parent) "..\VSCode-win32-x64"
  $target = Join-Path $studio "VajraAIStudio-win32-x64"
  if (Test-Path $out) {
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Move-Item $out $target
    Write-Host "`n-> $target" -ForegroundColor Green
  }
} finally { Pop-Location }
