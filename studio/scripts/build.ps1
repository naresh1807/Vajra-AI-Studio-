<#
  Compiles Vajra AI Studio from the bootstrapped fork.
    scripts\build.ps1            -> studio\VajraAIStudio-win32-x64\  (portable folder)
    scripts\build.ps1 -Setup     -> also studio\VajraAIStudioSetup-x64.exe  (Inno installer)
  ~25-45 min first time.
#>
param([switch]$Setup, [switch]$SkipCompile)

$ErrorActionPreference = "Stop"
$studio = Split-Path $PSScriptRoot -Parent
$bdFile = Join-Path $studio ".builddir"
$buildDir = if (Test-Path $bdFile) { (Get-Content $bdFile).Trim() } else { "C:\vajra-studio-build" }
$vscode = Join-Path $buildDir "vscode"
if (-not (Test-Path (Join-Path $vscode "node_modules"))) { throw "Run scripts\bootstrap.ps1 first." }
$out = Join-Path $buildDir "VSCode-win32-x64"
$target = Join-Path $studio "VajraAIStudio-win32-x64"

if (-not $SkipCompile) {
  # re-apply our patches (in case of an upstream checkout) then gulp-build
  node (Join-Path $PSScriptRoot "apply-overrides.mjs") $vscode
  $mk = if (Test-Path (Join-Path $vscode ".vajra-marketplace")) { (Get-Content (Join-Path $vscode ".vajra-marketplace")).Trim() } else { "openvsx" }
  node (Join-Path $PSScriptRoot "set-marketplace.mjs") $mk $vscode
  Copy-Item (Join-Path $PSScriptRoot "Directory.Build.targets") $vscode -Force
  robocopy (Join-Path (Split-Path $studio -Parent) "vscode-extension") (Join-Path $vscode "extensions\vajra") /MIR /XD node_modules src /XF *.vsix tsconfig.json .vscodeignore /NFL /NDL /NJH /NJS | Out-Null

  & (Join-Path $PSScriptRoot "_devenv-gulp.bat") $vscode
  if ($LASTEXITCODE -ne 0) { throw "gulp build failed" }
}

if ($Setup) {
  # the setup task needs the compiled app at <buildDir>\VSCode-win32-x64
  if (-not (Test-Path $out) -and (Test-Path $target)) { Move-Item $target $out }
  & (Join-Path $PSScriptRoot "_devenv-setup.bat") $vscode
  if ($LASTEXITCODE -ne 0) { throw "installer build failed" }
  $inst = Get-ChildItem (Join-Path $vscode ".build\win32\user-setup\*.exe") | Select-Object -First 1
  Copy-Item $inst.FullName (Join-Path $studio "VajraAIStudioSetup-x64.exe") -Force
  Write-Host "`n-> $(Join-Path $studio 'VajraAIStudioSetup-x64.exe')  ($([math]::Round($inst.Length/1MB,0)) MB)" -ForegroundColor Green
}

if (-not (Test-Path $target)) {
  if (-not (Test-Path $out)) { throw "expected build output at $out" }
  Move-Item $out $target
}
$exe = Get-ChildItem $target -Filter "*.exe" | Where-Object { $_.Name -notlike "*Crash*" } | Select-Object -First 1
Write-Host "`n-> `"$($exe.FullName)`"" -ForegroundColor Green
Write-Host "   or:  `"$target\bin\vajra-studio.cmd`" <folder>"
Write-Host "   NOTE: unset ELECTRON_RUN_AS_NODE in your shell first, or the exe runs as plain node."
