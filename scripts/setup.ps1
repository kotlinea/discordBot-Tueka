# Optional Docker readiness check only. Run tasks with compose.tools.yaml.
$ErrorActionPreference = 'Stop'
if ($args.Count -gt 0) { throw 'This script only checks Docker. Use: docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup <action> <arguments>' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop with Compose, start it, and select Linux containers. See handbook/operator/setup.md.'
}
docker compose version
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is required.' }
$endpoint = if ($env:DOCKER_HOST) { $env:DOCKER_HOST } else { docker context inspect --format '{{.Endpoints.docker.Host}}' }
if ($endpoint -match '^(ssh|tcp)://') { throw 'Select a local Docker Engine/Desktop context. Remote Docker is unsupported.' }
$containerOS = docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $containerOS -ne 'linux') {
    throw 'Start Docker Desktop and select Linux containers, then rerun this check.'
}
Write-Output 'Docker is ready. Run: docker compose -f compose.tools.yaml run --rm --build check'
