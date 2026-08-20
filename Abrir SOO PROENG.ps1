$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\Neverton\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$url = "http://127.0.0.1:8775"

Set-Location $root

$listening = netstat -ano | Select-String ":8775"
if (-not $listening) {
    Start-Process -FilePath $python -ArgumentList "app.py" -WorkingDirectory $root -WindowStyle Normal
    Start-Sleep -Seconds 2
}

Start-Process $url
