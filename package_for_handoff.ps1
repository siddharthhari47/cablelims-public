<#
Builds a clean, self-contained CableLIMS package ready to copy onto a drive
(first handoff) or send as an update (he applies it over his existing
install). Deliberately EXCLUDES anything machine-specific or data-bearing:
  - backend\venv          (rebuilt fresh on his PC by first_time_setup.bat)
  - frontend\node_modules (not needed on his PC at all -- we ship the build)
  - backend\data          (his database + secret key -- NEVER ship ours,
                            NEVER overwrite his)
  - backend\certificates, backend\uploads (his generated files)
  - __pycache__, .pyc

Run this from the cablelims project root (where this script lives).
Output: a timestamped zip in .\handoff_packages\, plus the unzipped folder.

For the FIRST handoff: send the whole zip, he runs first_time_setup.bat.
For an UPDATE later: send the whole zip again -- he extracts it over his
existing folder (see UPDATING.md), overwriting only code, never his data,
because this zip never contains a data folder in the first place.
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$pkgName = "cablelims_$stamp"
$outDir = Join-Path $root "handoff_packages\$pkgName"
$zipPath = Join-Path $root "handoff_packages\$pkgName.zip"

Write-Host "=== Building frontend ===" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
npm run build
Pop-Location

if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
New-Item -ItemType Directory -Path $outDir | Out-Null

Write-Host "=== Copying backend source (code only, no venv/data) ===" -ForegroundColor Cyan
$backendOut = Join-Path $outDir "backend"
New-Item -ItemType Directory -Path $backendOut | Out-Null
Copy-Item (Join-Path $root "backend\app") (Join-Path $backendOut "app") -Recurse -Exclude "__pycache__"
Get-ChildItem -Path (Join-Path $backendOut "app") -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path (Join-Path $backendOut "app") -Recurse -Filter "*.pyc" | Remove-Item -Force
Copy-Item (Join-Path $root "backend\requirements.txt") $backendOut
# H13: requirements.lock.txt pins the full resolved dependency tree --
# first_time_setup.bat installs from it when present, so it must ship too.
Copy-Item (Join-Path $root "backend\requirements.lock.txt") $backendOut

# H3: Alembic migrations. Both are required at startup -- app.db_migrate.run_migrations()
# loads backend\alembic.ini and walks backend\alembic\versions\*.py to bring a fresh or
# out-of-date database up to the current schema. Neither is data-bearing (no database
# contents live here, just migration *code*), so both ship with every package like app\.
Copy-Item (Join-Path $root "backend\alembic") (Join-Path $backendOut "alembic") -Recurse -Exclude "__pycache__"
Get-ChildItem -Path (Join-Path $backendOut "alembic") -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path (Join-Path $backendOut "alembic") -Recurse -Filter "*.pyc" | Remove-Item -Force
Copy-Item (Join-Path $root "backend\alembic.ini") $backendOut

# H14: the template an operator copies to backend\.env to override any
# setting (see app\config.py). Not data-bearing -- a real .env, if the
# operator creates one, stays on their machine, same as backend\data\.
Copy-Item (Join-Path $root "backend\.env.example") $backendOut

# B3 (Review #2 remediation): the test suite existed all along but never
# shipped in the package -- a comment saying "proven by the golden-value
# test suite" is not evidence if the recipient has no suite to run. tests/
# and requirements-dev.txt are code, not data, same category as app\ above.
Copy-Item (Join-Path $root "backend\tests") (Join-Path $backendOut "tests") -Recurse -Exclude "__pycache__"
Get-ChildItem -Path (Join-Path $backendOut "tests") -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path (Join-Path $backendOut "tests") -Recurse -Filter "*.pyc" | Remove-Item -Force
Copy-Item (Join-Path $root "backend\requirements-dev.txt") $backendOut

Write-Host "=== Copying built frontend ===" -ForegroundColor Cyan
Copy-Item (Join-Path $root "frontend\dist") (Join-Path $outDir "frontend\dist") -Recurse

Write-Host "=== Copying launchers and docs ===" -ForegroundColor Cyan
Copy-Item (Join-Path $root "start_cablelims.bat") $outDir
Copy-Item (Join-Path $root "first_time_setup.bat") $outDir
Copy-Item (Join-Path $root "backup_now.bat") $outDir
Copy-Item (Join-Path $root "run_tests.bat") $outDir
foreach ($doc in @("README.md", "DEPLOYMENT.md", "SELF_HOST_GUIDE.md", "UPDATING.md", "CableLIMS_SDD_v2.md")) {
    $p = Join-Path $root $doc
    if (Test-Path $p) { Copy-Item $p $outDir }
}

# B4 (Review #2 remediation): the Caddyfile template DEPLOYMENT.md step 7
# has the operator copy and edit -- not data-bearing (no secrets, no
# machine-specific values beyond the one placeholder address the operator
# fills in themselves), same category as everything else copied above.
Copy-Item (Join-Path $root "deploy") (Join-Path $outDir "deploy") -Recurse

Write-Host "=== Zipping ===" -ForegroundColor Cyan
Compress-Archive -Path "$outDir\*" -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Package ready:" -ForegroundColor Green
Write-Host "  Folder: $outDir"
Write-Host "  Zip:    $zipPath"
Write-Host ""
Write-Host "First handoff: copy the zip to a drive, send SELF_HOST_GUIDE.md instructions."
Write-Host "An update: send the zip again, he follows UPDATING.md (his data is untouched)."
