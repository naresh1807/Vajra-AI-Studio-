<#
  Headless sanity check on a built Vajra AI Studio tree (studio\build.ps1 output).
  Verifies: the CLI reports a version, product.json is rebranded, and the Vajra
  extension is bundled as a built-in. Does NOT open a window.

    scripts\smoke.ps1                       # checks studio\VajraAIStudio-win32-x64
    scripts\smoke.ps1 -Tree D:\some\build   # checks an explicit tree
#>
param([string]$Tree)

$ErrorActionPreference = "Stop"
$studio = Split-Path $PSScriptRoot -Parent
if (-not $Tree) { $Tree = Join-Path $studio "VajraAIStudio-win32-x64" }
if (-not (Test-Path $Tree)) { throw "no build at $Tree - run scripts\build.ps1 first" }

# ELECTRON_RUN_AS_NODE makes the exe behave as plain node and reject --version.
if ($env:ELECTRON_RUN_AS_NODE) { Remove-Item Env:ELECTRON_RUN_AS_NODE }

$fail = 0
function ok($m)   { Write-Host "  ok   $m" -ForegroundColor Green }
function bad($m)  { Write-Host "  FAIL $m" -ForegroundColor Red; $script:fail++ }

$cli = Join-Path $Tree "bin\vajra-studio.cmd"
if (Test-Path $cli) {
  $out = (& $cli --version 2>&1)          # capture fully first - piping to Select-First kills the child
  $rc = $LASTEXITCODE
  $v = ($out | Select-Object -First 1)
  if ($rc -eq 0 -and "$v" -match '^\d+\.\d+\.\d+') { ok "CLI --version -> $v" } else { bad "CLI --version (rc=$rc, '$v')" }
} else { bad "missing $cli" }

$pj = Join-Path $Tree "resources\app\product.json"
if (Test-Path $pj) {
  $p = Get-Content $pj -Raw | ConvertFrom-Json
  if ($p.nameLong -eq "Vajra AI Studio") { ok "product.json nameLong" } else { bad "product.json not rebranded ($($p.nameLong))" }
  if ($p.applicationName -eq "vajra-studio") { ok "product.json applicationName" } else { bad "applicationName ($($p.applicationName))" }
  if (-not $p.enableTelemetry) { ok "telemetry disabled" } else { bad "telemetry still enabled" }
} else { bad "missing $pj" }

$ext = Join-Path $Tree "resources\app\extensions\vajra\package.json"
if (Test-Path $ext) {
  $e = Get-Content $ext -Raw | ConvertFrom-Json
  ok "bundled extension vajra-ai@$($e.version)"
} else { bad "Vajra extension not bundled at resources\app\extensions\vajra" }

if ($fail) { Write-Host "`n$fail check(s) failed." -ForegroundColor Red; exit 1 }
Write-Host "`nAll smoke checks passed." -ForegroundColor Green
