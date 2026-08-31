<#
  Compiles Vajra AI Studio from the bootstrapped fork.
    scripts\build.ps1            -> studio\VajraAIStudio-win32-x64\  (portable folder)
    scripts\build.ps1 -Setup     -> also studio\VajraAIStudioSetup-x64.exe  (Inno installer)
  ~25-45 min first time.
#>
param([switch]$Setup, [switch]$SkipCompile)

$ErrorActionPreference = "Stop"

# Recursively delete a tree that may contain paths longer than MAX_PATH (the
# bundled copilot extension nests node_modules deep enough that Remove-Item
# -Recurse throws). robocopy mirrors an empty dir over it first, then the husk
# deletes cleanly. Best-effort: a locked file (OneDrive / indexer) is tolerated.
function Remove-Tree($path) {
  if (-not (Test-Path $path)) { return }
  $empty = Join-Path $env:TEMP "vajra-empty-$PID"
  New-Item -ItemType Directory -Force -Path $empty | Out-Null
  robocopy $empty $path /MIR /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
  Remove-Item $path  -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $empty -Recurse -Force -ErrorAction SilentlyContinue
}

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
  node (Join-Path $PSScriptRoot "patch-fork.mjs") $vscode
  node (Join-Path $PSScriptRoot "apply-icons.mjs") $vscode
  Copy-Item (Join-Path $PSScriptRoot "Directory.Build.targets") $vscode -Force
  robocopy (Join-Path (Split-Path $studio -Parent) "vscode-extension") (Join-Path $vscode "extensions\vajra") /MIR /XD node_modules src /XF *.vsix tsconfig.json .vscodeignore /NFL /NDL /NJH /NJS | Out-Null

  & (Join-Path $PSScriptRoot "_devenv-gulp.bat") $vscode
  if ($LASTEXITCODE -ne 0) { throw "gulp build failed" }

  # the fresh compile lands at $out - it supersedes any previous $target so a
  # rebuild doesn't silently keep serving the old app folder. Rename the stale
  # one aside first (instant, same volume) so the move below always succeeds.
  if ((Test-Path $out) -and (Test-Path $target)) {
    $stale = "$target.stale-$(Get-Date -Format yyyyMMddHHmmss)"
    Move-Item $target $stale
    Remove-Tree $stale
  }
}

if ($Setup) {
  # the setup task needs the compiled app at <buildDir>\VSCode-win32-x64
  if (-not (Test-Path $out) -and (Test-Path $target)) { Move-Item $target $out }
  & (Join-Path $PSScriptRoot "_devenv-setup.bat") $vscode
  if ($LASTEXITCODE -ne 0) { throw "installer build failed" }
  $inst = Get-ChildItem (Join-Path $vscode ".build\win32-x64\user-setup\*.exe"),(Join-Path $vscode ".build\win32\user-setup\*.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
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
