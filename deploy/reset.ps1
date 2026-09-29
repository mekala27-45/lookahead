# The reset half of reset and rederive, from a Windows machine: delete the forecasts the recording,
# the persistence check, the verification and the replay created in the live log, by their stated
# notes, with their rows and scores, and leave the audit log alone.
#
# Uses Neon's HTTP SQL endpoint (https://<host>/sql with the connection string in the
# Neon-Connection-String header), because this machine has no psql. Reads the connection string
# from the .env beside the repository, the same file deploy.ps1 reads, and uses the `lookahead`
# schema when the string is the shared DATABASE_URL. Writes what it removed to
# deploy\reset-result.json.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\reset.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

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

if ($env:LOOKAHEAD_DATABASE_URL) { $connection = $env:LOOKAHEAD_DATABASE_URL; $prefix = "" }
elseif ($env:DATABASE_URL) { $connection = $env:DATABASE_URL; $prefix = "lookahead." }
else { throw "neither LOOKAHEAD_DATABASE_URL nor DATABASE_URL is set" }

# psycopg's scheme is not what Neon's HTTP endpoint expects.
$connection = $connection -replace '^postgresql\+psycopg://', 'postgresql://'
$hostName = ([Uri]$connection).Host
$endpoint = "https://$hostName/sql"
$headers = @{ "Neon-Connection-String" = $connection; "Neon-Raw-Text-Output" = "true"; "Neon-Array-Mode" = "false" }

function Invoke-Sql($query, $params) {
    $body = @{ query = $query; params = @($params) } | ConvertTo-Json -Depth 5
    return Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -ContentType "application/json" -TimeoutSec 90 -Body $body
}

$notes = @("recorded session for the control room", "persistence check", "verification from a separate client", "replay from a separate client")
$list = "'" + ($notes -join "','") + "'"
$before = Invoke-Sql "select count(*)::int as n from ${prefix}forecasts where note in ($list)" @()
$scores = Invoke-Sql "delete from ${prefix}scores where forecast_id in (select forecast_id from ${prefix}forecasts where note in ($list))" @()
$rows = Invoke-Sql "delete from ${prefix}forecast_rows where forecast_id in (select forecast_id from ${prefix}forecasts where note in ($list))" @()
$forecasts = Invoke-Sql "delete from ${prefix}forecasts where note in ($list)" @()
$after = Invoke-Sql "select count(*)::int as n from ${prefix}forecasts" @()
$result = [ordered]@{
    reset_at = (Get-Date).ToUniversalTime().ToString("o")
    matched = $before.rows[0].n
    deleted = @{ scores = $scores.rowCount; rows = $rows.rowCount; forecasts = $forecasts.rowCount }
    remaining_forecasts = $after.rows[0].n
    audit_log = "left alone"
}
$result | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "deploy\reset-result.json")
$result | ConvertTo-Json -Depth 5
Write-Host "reset: removed the forecasts the checks and the recording issued; the audit log keeps them"
