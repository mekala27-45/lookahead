# Fill the live log from a separate client: issue one forecast per served authority at the latest
# origin the server's data allows, then score them all, so the control room's forecast pages have a
# log to show. Writes what the server answered to results\deploy\replay.json.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\replay.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$base = (Get-Content (Join-Path $repo "deploy\live-url.txt") -Raw).Trim()
$token = (Get-Content (Join-Path $repo "deploy\write-token.txt") -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }

$authorities = (Invoke-RestMethod -Uri "$base/v1/authorities" -TimeoutSec 90).authorities
$issued = @()
foreach ($a in $authorities) {
    $r = Invoke-RestMethod -Method Post -Uri "$base/v1/forecasts" -Headers $headers -ContentType "application/json" -TimeoutSec 120 -Body (@{
        authority = $a.authority; note = "replay from a separate client"
    } | ConvertTo-Json -Depth 5)
    $issued += [ordered]@{ authority = $a.authority; forecast_id = $r.forecast_id; origin = $r.origin; model_version = $r.model_version }
    Write-Host "issued $($a.authority) at $($r.origin): $($r.forecast_id)"
}
$scored = Invoke-RestMethod -Method Post -Uri "$base/v1/score" -Headers $headers -ContentType "application/json" -TimeoutSec 180 -Body (@{ note = "replay from a separate client" } | ConvertTo-Json)
$card = Invoke-RestMethod -Uri "$base/v1/scorecard" -TimeoutSec 90
$result = [ordered]@{
    base_url = $base
    replayed_at = (Get-Date).ToUniversalTime().ToString("o")
    issued = $issued.Count
    scored_rows = $scored.scored_rows
    unscored_share = $scored.unscored_share
    scorecard = @{ forecasts = $card.forecasts; scored_rows = $card.scored_rows; mape = $card.mape; coverage_90 = $card.coverage_90; coverage_50 = $card.coverage_50 }
}
New-Item -ItemType Directory -Force -Path (Join-Path $repo "results\deploy") | Out-Null
$result | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "results\deploy\replay.json")
$result | ConvertTo-Json -Depth 5
Write-Host "replayed: $($issued.Count) forecasts issued and scored on the live log"
