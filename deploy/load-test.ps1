# The load test against the live API from a separate client (a Windows machine): one warming
# request, then N sequential POST /v1/forecasts and GET /v1/forecasts/{id}, then a burst of
# concurrent issues, timed with a stopwatch. Writes results\latency\live.json in the same shape as
# scripts/load_test.py, which the registry's latency gate and the documents read.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\load-test.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$base = (Get-Content (Join-Path $repo "deploy\live-url.txt") -Raw).Trim()
$token = (Get-Content (Join-Path $repo "deploy\write-token.txt") -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }
$requests = 40
$concurrency = 6

function Summary($samples) {
    $sorted = $samples | Sort-Object
    $n = $sorted.Count
    $p99Index = [Math]::Min($n - 1, [Math]::Max(0, [int][Math]::Round(0.99 * ($n - 1))))
    $p50 = if ($n % 2 -eq 1) { $sorted[[int](($n - 1) / 2)] } else { ($sorted[[int]($n / 2) - 1] + $sorted[[int]($n / 2)]) / 2 }
    return [ordered]@{ p50_ms = [Math]::Round($p50, 1); p99_ms = [Math]::Round($sorted[$p99Index], 1); max_ms = [Math]::Round($sorted[$n - 1], 1); mean_ms = [Math]::Round(($sorted | Measure-Object -Average).Average, 1) }
}

$authorities = (Invoke-RestMethod -Uri "$base/v1/authorities" -TimeoutSec 120).authorities | ForEach-Object { $_.authority }
$sw = [Diagnostics.Stopwatch]::StartNew()
$null = Invoke-RestMethod -Method Post -Uri "$base/v1/forecasts" -Headers $headers -ContentType "application/json" -TimeoutSec 120 -Body (@{ authority = $authorities[0]; note = "load test" } | ConvertTo-Json)
$wake = $sw.Elapsed.TotalMilliseconds
$issues = @(); $ids = @()
for ($i = 0; $i -lt $requests; $i++) {
    $a = $authorities[$i % $authorities.Count]
    $sw.Restart()
    $r = Invoke-RestMethod -Method Post -Uri "$base/v1/forecasts" -Headers $headers -ContentType "application/json" -TimeoutSec 120 -Body (@{ authority = $a; note = "load test" } | ConvertTo-Json)
    $issues += $sw.Elapsed.TotalMilliseconds
    $ids += $r.forecast_id
}
$reads = @()
foreach ($id in $ids) {
    $sw.Restart()
    $null = Invoke-RestMethod -Uri "$base/v1/forecasts/$id" -TimeoutSec 60
    $reads += $sw.Elapsed.TotalMilliseconds
}
$jobs = @()
for ($i = 0; $i -lt $concurrency; $i++) {
    $a = $authorities[$i % $authorities.Count]
    $jobs += Start-Job -ScriptBlock {
        param($base, $token, $a)
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $null = Invoke-RestMethod -Method Post -Uri "$base/v1/forecasts" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -TimeoutSec 120 -Body (@{ authority = $a; note = "load test" } | ConvertTo-Json)
        return $sw.Elapsed.TotalMilliseconds
    } -ArgumentList $base, $token, $a
}
$burst = $jobs | Wait-Job | Receive-Job
$jobs | Remove-Job
$result = [ordered]@{
    base_url = $base
    measured_at = (Get-Date).ToUniversalTime().ToString("o")
    requests = $requests
    concurrency = $concurrency
    authorities = $authorities.Count
    first_request_ms = [Math]::Round($wake, 1)
    issue = Summary $issues
    read = Summary $reads
    burst_issue_max_ms = [Math]::Round(($burst | Measure-Object -Maximum).Maximum, 1)
    errors = 0
    note = "sequential requests after one warming request from a Windows client; the burst is concurrent issues"
}
New-Item -ItemType Directory -Force -Path (Join-Path $repo "results\latency") | Out-Null
$result | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "results\latency\live.json")
$result | ConvertTo-Json -Depth 5
Write-Host "load test: $requests issues and reads against $base"
