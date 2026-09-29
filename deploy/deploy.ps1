# Deploy the lookahead API to Fly from a Windows machine.
#
# Reads FLY_API_TOKEN, LOOKAHEAD_DATABASE_URL (or DATABASE_URL, in which case the tables go in the
# `lookahead` schema of that database, so another project's tables there are never touched) and
# LOOKAHEAD_WRITE_TOKEN from a .env file next to the repository (C:\Project FullTime\.env by
# default) or from the environment, installs flyctl when it is missing, creates the app when it
# does not exist, stages the secrets, deploys with Fly's remote builder (no local Docker), then
# checks the live health endpoint and writes everything it saw to deploy\deploy-log.txt so the
# build can read the result back. Secrets are never printed.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\deploy.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$log = Join-Path $repo "deploy\deploy-log.txt"
Start-Transcript -Path $log -Force | Out-Null

function Read-DotEnv($path) {
    if (Test-Path $path) {
        Get-Content $path | ForEach-Object {
            if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
                $name = $matches[1]; $value = $matches[2].Trim().Trim('"').Trim("'")
                if (-not [string]::IsNullOrEmpty($value)) { [Environment]::SetEnvironmentVariable($name, $value, "Process") }
            }
        }
    }
}

Read-DotEnv (Join-Path (Split-Path -Parent $repo) ".env")
Read-DotEnv (Join-Path $repo ".env")

$app = if ($env:LOOKAHEAD_FLY_APP_NAME) { $env:LOOKAHEAD_FLY_APP_NAME } else { "lookahead-grid-api" }
$schema = ""
if ($env:LOOKAHEAD_DATABASE_URL) {
    $url = $env:LOOKAHEAD_DATABASE_URL
    Write-Host "database: LOOKAHEAD_DATABASE_URL, default schema"
} elseif ($env:DATABASE_URL) {
    $url = $env:DATABASE_URL
    $schema = "lookahead"
    Write-Host "database: DATABASE_URL, schema lookahead"
} else {
    throw "neither LOOKAHEAD_DATABASE_URL nor DATABASE_URL (the Neon connection string) is set"
}
if (-not $env:LOOKAHEAD_WRITE_TOKEN) { $env:LOOKAHEAD_WRITE_TOKEN = [guid]::NewGuid().ToString("N") }

$fly = Get-Command flyctl -ErrorAction SilentlyContinue
if (-not $fly) {
    $candidate = Join-Path $env:USERPROFILE ".fly\bin\flyctl.exe"
    if (-not (Test-Path $candidate)) {
        Write-Host "installing flyctl"
        Invoke-WebRequest -UseBasicParsing https://fly.io/install.ps1 | Invoke-Expression
    }
    $env:Path = "$env:USERPROFILE\.fly\bin;$env:Path"
}
flyctl version

$apps = flyctl apps list --json | ConvertFrom-Json
if (-not ($apps | Where-Object { $_.Name -eq $app })) {
    Write-Host "creating app $app"
    flyctl apps create $app --org personal
}

Set-Location $repo
flyctl secrets set --app $app --stage "DATABASE_URL=$url" "LOOKAHEAD_WRITE_TOKEN=$env:LOOKAHEAD_WRITE_TOKEN" "LOOKAHEAD_DB_SCHEMA=$schema"
flyctl deploy --app $app --remote-only --ha=false

$base = "https://$app.fly.dev"
Write-Host "checking $base/v1/health"
$health = $null
for ($i = 0; $i -lt 12 -and -not $health; $i++) {
    try { $health = Invoke-RestMethod -Uri "$base/v1/health" -TimeoutSec 60 } catch { Start-Sleep -Seconds 10 }
}
if (-not $health) { throw "the API did not answer at $base/v1/health" }
$health | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $repo "deploy\live-url.txt") -Value $base
Set-Content -Path (Join-Path $repo "deploy\write-token.txt") -Value $env:LOOKAHEAD_WRITE_TOKEN
Write-Host "deployed: $base"
Stop-Transcript | Out-Null
