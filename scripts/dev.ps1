# Windows mirror of the Makefile, plus a portable-PostgreSQL fallback for
# machines without Docker. Usage:  powershell -File scripts\dev.ps1 <task>
#
# Tasks: setup | run | worker | migrate | makemigrations | test | superuser
#        db-install | db-init | db-start | db-stop | db-status

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Task,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$Py   = Join-Path $Venv 'Scripts\python.exe'

# Portable PostgreSQL (used only when Docker/system Postgres is unavailable)
$PgVersion = '16.9-1'
$PgDir     = Join-Path $Root '.pg\pgsql'
$PgData    = Join-Path $Root '.pg\data'
$PgLog     = Join-Path $Root '.pg\postgres.log'
$PgBin     = Join-Path $PgDir 'bin'

function Invoke-Manage {
    param([string[]]$ManageArgs)
    if (-not (Test-Path $Py)) { throw "No .venv found. Run: scripts\dev.ps1 setup" }
    Push-Location $Root
    try { & $Py manage.py @ManageArgs; if ($LASTEXITCODE -ne 0) { throw "manage.py $($ManageArgs -join ' ') failed" } }
    finally { Pop-Location }
}

switch ($Task) {
    'setup' {
        Push-Location $Root
        try {
            if (-not (Test-Path $Py)) { py -3.11 -m venv $Venv }
            & (Join-Path $Venv 'Scripts\pip.exe') install -r requirements.txt
            if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
            if (-not (Test-Path (Join-Path $Root '.env'))) {
                Copy-Item (Join-Path $Root '.env.example') (Join-Path $Root '.env')
                Write-Host 'Created .env from .env.example — edit SECRET_KEY before deploying anywhere.'
            }
        } finally { Pop-Location }
    }
    'run'            { Invoke-Manage @('runserver', '0.0.0.0:8000') }
    'worker'         { Invoke-Manage @('qcluster') }
    'migrate'        { Invoke-Manage (@('migrate') + $Rest) }
    'makemigrations' { Invoke-Manage (@('makemigrations') + $Rest) }
    'test'           { Invoke-Manage (@('test', 'apps') + $Rest) }
    'superuser'      { Invoke-Manage @('createsuperuser') }

    'db-install' {
        if (Test-Path $PgBin) { Write-Host "Portable PostgreSQL already at $PgDir"; break }
        $zip = Join-Path $env:TEMP "pg-$PgVersion-binaries.zip"
        $url = "https://get.enterprisedb.com/postgresql/postgresql-$PgVersion-windows-x64-binaries.zip"
        Write-Host "Downloading $url ..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $zip
        Write-Host 'Extracting...'
        New-Item -ItemType Directory -Force (Join-Path $Root '.pg') | Out-Null
        Expand-Archive -Path $zip -DestinationPath (Join-Path $Root '.pg') -Force
        Remove-Item $zip -Confirm:$false
        Write-Host "Installed to $PgDir"
    }
    'db-init' {
        if (Test-Path $PgData) { Write-Host "Data dir already exists: $PgData"; break }
        # Trust auth is acceptable here: dev-only server bound to 127.0.0.1.
        & (Join-Path $PgBin 'initdb.exe') -U postgres -A trust -E UTF8 -D $PgData
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
        Write-Host 'Initialized. Start it with: scripts\dev.ps1 db-start'
    }
    'db-start' {
        & (Join-Path $PgBin 'pg_ctl.exe') -D $PgData -l $PgLog -o '-p 5432 -h 127.0.0.1' start
        if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed (see $PgLog)" }
        # Create the app database on first run.
        $exists = & (Join-Path $PgBin 'psql.exe') -U postgres -h 127.0.0.1 -tAc "SELECT 1 FROM pg_database WHERE datname='industry_rockstar'"
        if ($exists -ne '1') {
            & (Join-Path $PgBin 'createdb.exe') -U postgres -h 127.0.0.1 industry_rockstar
            Write-Host 'Created database industry_rockstar.'
        }
    }
    'db-stop'   { & (Join-Path $PgBin 'pg_ctl.exe') -D $PgData stop }
    'db-status' { & (Join-Path $PgBin 'pg_ctl.exe') -D $PgData status }

    default { throw "Unknown task '$Task'. See header of scripts/dev.ps1 for the list." }
}
