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

$reloadArg = ""
if ($Reload.IsPresent) {
    $reloadArg = "--reload"
}

$url = "http://$HostName`:$Port/dev"
Write-Host "Opening browser: $url"
Start-Process $url

Write-Host "Starting Dev UI server..."
if ($reloadArg) {
    & py $resolvedTag scripts/run_dev_ui.py --host $HostName --port $Port --reload
}
else {
    & py $resolvedTag scripts/run_dev_ui.py --host $HostName --port $Port
}
