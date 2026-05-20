param(
    [switch]$Freeze,
    [switch]$NoAttach
)

$ErrorActionPreference = "Stop"

Write-Host "Starting containers..."
docker compose up -d --build

if ($Freeze) {
    Write-Host "Starting freeze client (demo timeout)..."
    docker compose --profile demo up -d --build target_freeze
}

if (-not $NoAttach) {
    Write-Host "Attaching to operator client: operator"
    Write-Host "Detach without stopping: Ctrl+P then Ctrl+Q"
    docker attach operator
}
