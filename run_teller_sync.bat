@echo off
:: Weekly Teller transaction sync.
:: Pulls the last 30 days of transactions/balances into Postgres so the daily
:: payment reminder always has fresh data. Overlap is deduped by the sync route.
::
:: Schedule with Windows Task Scheduler to run weekly (e.g. Monday 7:00 AM).
:: Requires the backend to be running: docker compose up -d db backend

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$from = (Get-Date).AddDays(-30).ToString('yyyy-MM-dd');" ^
  "$to   = (Get-Date).ToString('yyyy-MM-dd');" ^
  "$body = @{ from_date = $from; to_date = $to } | ConvertTo-Json;" ^
  "try {" ^
  "  $r = Invoke-RestMethod -Uri 'http://localhost:8000/api/teller/sync' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180;" ^
  "  Write-Host ('[sync] ' + $r.message)" ^
  "} catch {" ^
  "  Write-Host ('[sync] FAILED: ' + $_.Exception.Message);" ^
  "  Write-Host '       Is the backend up? docker compose up -d db backend';" ^
  "  exit 1" ^
  "}"
