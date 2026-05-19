param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$Reload,
    [string]$PythonTag = "auto"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Using project root: $projectRoot"
Write-Host "Resolving Python launcher (>=3.10)..."

$resolvedTag = $PythonTag
if ($resolvedTag -eq "auto") {
    $candidates = @("-3.10", "-3.12", "-3.11", "-3.13")
    $resolvedTag = ""
    foreach ($candidate in $candidates) {
        try {
            $null = py $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                $resolvedTag = $candidate
                break
            }
        }
        catch {
            # ignore and try next candidate
        }
    }
}

if ([string]::IsNullOrWhiteSpace($resolvedTag)) {
    Write-Error "No supported Python found. Install Python 3.10+ or run with -PythonTag '-3.12'."
}

try {
    $pythonVersion = py $resolvedTag --version
    Write-Host "Detected runtime: $pythonVersion ($resolvedTag)"
}
catch {
    Write-Error "Selected Python launcher '$resolvedTag' is not available."
}

Write-Host "Installing requirements for dev UI..."
& py $resolvedTag -m pip install -r requirements.txt | Out-Host

function Test-PortFree {
    param(
        [string]$BindHost,
        [int]$BindPort
    )
    try {
        $ip = [System.Net.IPAddress]::Parse($BindHost)
    }
    catch {
        # Fallback: if host is not an IP literal, we don't preflight.
        return $true
    }
    try {
        $listener = [System.Net.Sockets.TcpListener]::new($ip, $BindPort)
        $listener.Start()
        $listener.Stop()
        return $true
    }
    catch {
        return $false
    }
}

$originalPort = $Port
for ($i = 0; $i -lt 10; $i++) {
    if (Test-PortFree -BindHost $HostName -BindPort $Port) {
        break
    }
    $Port = $Port + 1
}
if ($Port -ne $originalPort) {
    Write-Host "Port $originalPort is busy; using $Port instead."
}

$appUrl = "http://${HostName}:${Port}/app"

# Open the browser *after* the server has had time to bind (previously we opened it first — connection refused).
Write-Host "Will open browser in ~2s: $appUrl"
$openJob = Start-Job -ScriptBlock {
    param([string]$targetUrl)
    Start-Sleep -Seconds 2
    Start-Process $targetUrl
} -ArgumentList $appUrl

Write-Host "Starting Dev UI server (Ctrl+C to stop)..."
try {
    if ($Reload.IsPresent) {
        & py $resolvedTag scripts/run_dev_ui.py --host $HostName --port $Port --reload
    }
    else {
        & py $resolvedTag scripts/run_dev_ui.py --host $HostName --port $Port
    }
}
finally {
    if ($openJob -and $openJob.State -in @("Running", "NotStarted")) {
        Stop-Job -Job $openJob -ErrorAction SilentlyContinue
    }
    Remove-Job -Job $openJob -Force -ErrorAction SilentlyContinue
}
