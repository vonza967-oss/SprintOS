# Start SprintOS with the local launcher from the repo root.

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir
if (Get-Command python3 -ErrorAction SilentlyContinue) {
    python3 scripts/launch.py
} else {
    python scripts/launch.py
}
