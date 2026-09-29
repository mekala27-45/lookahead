# Verify the live API from a separate client (a Windows machine, not the server, not the build
# sandbox): issue a forecast for the first authority, score the log, read the forecast back with
# its rows and scores, read the audit log, and check the audit row was written before the issue
# response was served. Writes the transcript to deploy\verify-log.txt and the observation, with no
# secrets in it, to results\deploy\verification.json so the build can quote it.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\verify.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$log = Join-Path $repo "deploy\verify-log.txt"
Start-Transcript -Path $log -Force | Out-Null

$base = (Get-Content (Join-Path $repo "deploy\live-url.txt") -Raw).Trim()
$token = (Get-Content (Join-Path $repo "deploy\write-token.txt") -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }

Write-Host "client: $env:COMPUTERNAME ($([Environment]::OSVersion.VersionString)), PowerShell $($PSVersionTable.PSVersion)"
Write-Host "server: $base"

$health = Invoke-RestMethod -Uri "$base/v1/health" -TimeoutSec 90
Write-Host "health: status=$($health.status) database=$($health.database) model=$($health.model_version) backend=$($health.backend) authorities=$($health.authorities)"

$authorities = (Invoke-RestMethod -Uri "$base/v1/authorities" -TimeoutSec 90).authorities
$authority = $authorities[0].authority
Write-Host "issuing a forecast for $authority at origin $($authorities[0].latest_origin)"

$issued = Invoke-RestMethod -Method Post -Uri "$base/v1/forecasts" -Headers $headers -ContentType "application/json" -TimeoutSec 120 -Body (@{
    authority = $authority; note = "verification from a separate client"
} | ConvertTo-Json -Depth 5)
$forecastId = $issued.forecast_id
$servedAt = [DateTime]::Parse($issued.served_at).ToUniversalTime()
Write-Host "issued forecast $forecastId, $($issued.stored_rows) rows, model $($issued.model_version)"

$scored = Invoke-RestMethod -Method Post -Uri "$base/v1/score" -Headers $headers -ContentType "application/json" -TimeoutSec 120 -Body (@{
    note = "verification from a separate client"
} | ConvertTo-Json -Depth 5)
Write-Host "scored $($scored.scored_rows) rows across $($scored.forecasts_touched) forecasts, unscored share $($scored.unscored_share)"

$forecast = Invoke-RestMethod -Uri "$base/v1/forecasts/$forecastId" -TimeoutSec 90
$audit = Invoke-RestMethod -Uri "$base/v1/audit?limit=50" -TimeoutSec 90
$issue = $audit.entries | Where-Object { $_.action -eq "issue" -and $_.resource_id -eq $forecastId } | Select-Object -First 1
$auditAt = [DateTime]::Parse($issue.at).ToUniversalTime()
$auditBefore = $auditAt -le $servedAt

$ok = ($forecast.authority -eq $authority) -and ($forecast.rows.Count -eq 48) -and ($forecast.scores.Count -ge 1) -and $auditBefore -and ($forecast.statement.Length -gt 100)
$firstHour = ($forecast.rows | Sort-Object horizon | Select-Object -First 1).q50
$result = [ordered]@{
    base_url = $base
    client = "$env:COMPUTERNAME, Windows, PowerShell $($PSVersionTable.PSVersion)"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    health = @{ status = $health.status; database = $health.database; model_version = $health.model_version; backend = $health.backend; authorities = $health.authorities }
    authority = $authority
    origin = $forecast.origin
    model_version = $forecast.model_version
    backend = $forecast.backend
    forecast_id = $forecastId
    forecast_rows_read_back = $forecast.rows.Count
    median_first_hour_mw = $firstHour
    scores_read_back = $forecast.scores.Count
    scored_now = $scored.scored_rows
    scored_share = $forecast.scored_share
    unscored_share = $scored.unscored_share
    audit_entries = $audit.entries.Count
    audit_before_response = $auditBefore
    statement_present = ($forecast.statement.Length -gt 100)
    passed = $ok
}
New-Item -ItemType Directory -Force -Path (Join-Path $repo "results\deploy") | Out-Null
$result | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "results\deploy\verification.json")
$result | ConvertTo-Json -Depth 5
if (-not $ok) { throw "verification failed" }
Write-Host "verified: the forecast, its rows and its scores were read back from a separate client"
Stop-Transcript | Out-Null
