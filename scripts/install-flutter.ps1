<#
  Installs the Flutter SDK (user-scope, no admin) so the native Vajra Mobile
  APK can be built. Downloads the current stable channel to
  $env:USERPROFILE\dev\flutter and adds it to the user PATH.
#>
$ErrorActionPreference = 'Stop'

$dev = Join-Path $env:USERPROFILE 'dev'
New-Item -ItemType Directory -Force -Path $dev | Out-Null
$zip = Join-Path $dev 'flutter_sdk.zip'
$dest = Join-Path $dev 'flutter'

if (-not (Test-Path $zip)) {
  $manifest = Invoke-RestMethod 'https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json'
  $rel = $manifest.releases | Where-Object hash -eq $manifest.current_release.stable | Select-Object -First 1
  Write-Host "Downloading Flutter $($rel.version)..." -ForegroundColor Cyan
  Invoke-WebRequest "https://storage.googleapis.com/flutter_infra_release/releases/$($rel.archive)" -OutFile $zip
}

Write-Host "Extracting to $dest ..." -ForegroundColor Cyan
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Expand-Archive -Path $zip -DestinationPath $dev -Force

$bin = Join-Path $dest 'bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$bin*") {
  [Environment]::SetEnvironmentVariable('Path', "$userPath;$bin", 'User')
  Write-Host "Added $bin to user PATH (restart shells)." -ForegroundColor Green
}

& (Join-Path $bin 'flutter.bat') --version
Write-Host "`nNext:  flutter doctor --android-licenses   (accept)" -ForegroundColor Yellow
Write-Host "Then:  cd mobile-android/flutter_app; flutter create --org ai.vajra --project-name vajra_companion --platforms android . ; flutter build apk --release"
