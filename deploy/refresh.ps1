# Redeploy after the model exports changed (a new backtest wrote results\models), then verify again.
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\lookahead\deploy\refresh.ps1"
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& powershell -ExecutionPolicy Bypass -File (Join-Path $here "deploy.ps1")
& powershell -ExecutionPolicy Bypass -File (Join-Path $here "verify.ps1")
