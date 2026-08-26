$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$serverDir = Join-Path $root 'finance-server'
$python = Join-Path $root '.venv\Scripts\python.exe'
$adb = 'D:\DevTools\android-sdk\platform-tools\adb.exe'

$health = $null
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8766/api/v1/health' -TimeoutSec 2
} catch {
    $health = $null
}

if (-not $health) {
    Write-Host '启动 finance-server ...'
    Start-Process -FilePath $python `
        -ArgumentList '-m','uvicorn','server_app.main:app','--host','0.0.0.0','--port','8766' `
        -WorkingDirectory $serverDir -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

& $adb reverse tcp:8766 tcp:8766
Write-Host 'USB 反向转发已建立：手机可访问 http://127.0.0.1:8766'
& $adb reverse --list

$lan = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.IPAddress -notlike '172.*' -and
        $_.IPAddress -notlike '198.18.*'
    } |
    Select-Object -First 1
if ($lan) {
    Write-Host "局域网地址：http://$($lan.IPAddress):8766"
}
