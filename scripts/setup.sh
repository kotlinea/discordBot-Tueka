#!/bin/sh
# Optional Docker readiness check only. No dependency installation or delegation.
set -eu
if [ "$#" -ne 0 ]; then
    echo 'This script only checks Docker. Use: docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup <action> <arguments>' >&2
    exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
    echo 'Install Docker Engine/Desktop with Compose; see handbook/operator/setup.md.' >&2
    exit 1
fi
docker compose version
case "${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}" in
    ssh://*|tcp://*) echo 'Select a local Docker Engine/Desktop context. Remote Docker is unsupported.' >&2; exit 1 ;;
esac
if [ "$(docker info --format '{{.OSType}}')" != linux ]; then
    echo 'Start Docker and select Linux containers, then rerun this check.' >&2
    exit 1
fi
echo 'Docker is ready. Run: docker compose -f compose.tools.yaml run --rm --build check'
