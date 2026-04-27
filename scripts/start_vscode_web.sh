#!/usr/bin/env bash
set -euo pipefail

host="127.0.0.1"
port="8000"
folder="${1:-/home/dad/nvr/pipeline_config}"
url="http://${host}:${port}"

mkdir -p "${folder}"

if curl -fsS "${url}/" >/dev/null 2>&1; then
    echo "VS Code Web editor already running at ${url}"
    echo "Web UI available at ${url}"
    sleep infinity
fi

echo "Starting VS Code Web editor at ${url}"
exec code serve-web \
    --host "${host}" \
    --port "${port}" \
    --without-connection-token \
    --accept-server-license-terms \
    --default-folder "${folder}"
