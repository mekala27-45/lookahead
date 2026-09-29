# Read the live API's recent logs from Fly on a Windows machine, so a failing health check can be
# explained without opening a dashboard. Reads FLY_API_TOKEN from C:\Project FullTime\.env (or the
# environment), asks flyctl for the log tail, redacts anything that looks like a connection string
# or a bearer token, and writes the result to deploy\fly-logs.txt.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\logs.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$out = Join-Path $repo "deploy\fly-logs.txt"

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
if (-not (Get-Command flyctl -ErrorAction SilentlyContinue)) { $env:Path = "$env:USERPROFILE\.fly\bin;$env:Path" }

$lines = flyctl logs --app $app --no-tail 2>&1 | ForEach-Object { "$_" }
$redacted = $lines | ForEach-Object {
    $_ -replace 'postgres(ql)?(\+[a-z]+)?://[^\s"]+', 'postgresql://REDACTED' `
       -replace '(?i)bearer\s+[A-Za-z0-9._-]+', 'Bearer REDACTED' `
       -replace '(?i)(token[=:]\s*)[A-Za-z0-9._-]+', '$1REDACTED'
}
$redacted | Set-Content -Path $out
Write-Host "wrote $($redacted.Count) lines to deploy\fly-logs.txt"
$redacted | Select-Object -Last 40
