# NEXUS one-command startup (Windows)
# Starts the platform server. Workers are added in a later phase.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "venv")) {
    python -m venv venv
}

& .\venv\Scripts\Activate.ps1
python -m pip install -q -r requirements.txt
python -m nexus.run
