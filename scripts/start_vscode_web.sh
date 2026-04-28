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
code serve-web \
    --host "${host}" \
    --port "${port}" \
    --without-connection-token \
    --accept-server-license-terms \
    --default-folder "${folder}" &

server_pid="$!"

cleanup() {
    kill "${server_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in {1..100}; do
    if curl -fsS "${url}/" >/dev/null 2>&1; then
        echo "Web UI available at ${url}"
        wait "${server_pid}"
        exit $?
    fi

    if ! kill -0 "${server_pid}" >/dev/null 2>&1; then
        wait "${server_pid}"
        exit $?
    fi

    sleep 0.1
done

echo "Timed out waiting for VS Code Web editor at ${url}" >&2
exit 1
