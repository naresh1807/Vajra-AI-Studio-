<#
  Compiles Vajra AI Studio from the bootstrapped fork.
  Output: studio\VajraAIStudio-win32-x64\  (run VajraAIStudio.exe).  ~30-45 min first time.
#>
$ErrorActionPreference = "Stop"
$studio = Split-Path $PSScriptRoot -Parent
$bdFile = Join-Path $studio ".builddir"
$buildDir = if (Test-Path $bdFile) { (Get-Content $bdFile).Trim() } else { "C:\vajra-studio-build" }
$vscode = Join-Path $buildDir "vscode"
if (-not (Test-Path (Join-Path $vscode "node_modules"))) { throw "Run scripts\bootstrap.ps1 first." }

# re-apply our patches (in case of an upstream checkout) then gulp-build
node (Join-Path $PSScriptRoot "apply-overrides.mjs") $vscode
$mk = if (Test-Path (Join-Path $vscode ".vajra-marketplace")) { (Get-Content (Join-Path $vscode ".vajra-marketplace")).Trim() } else { "openvsx" }
node (Join-Path $PSScriptRoot "set-marketplace.mjs") $mk $vscode
Copy-Item (Join-Path $PSScriptRoot "Directory.Build.targets") $vscode -Force

& (Join-Path $PSScriptRoot "_devenv-gulp.bat") $vscode
if ($LASTEXITCODE -ne 0) { throw "gulp build failed" }

$out = Join-Path $buildDir "VSCode-win32-x64"
$target = Join-Path $studio "VajraAIStudio-win32-x64"
if (Test-Path $out) {
  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  Move-Item $out $target
  Write-Host "`n-> $target\VajraAIStudio.exe" -ForegroundColor Green
} else {
  throw "expected build output at $out"
}
