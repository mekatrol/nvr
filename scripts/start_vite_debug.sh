#!/usr/bin/env bash
set -euo pipefail

host="127.0.0.1"
port="5173"
url="http://${host}:${port}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if curl -fsS "${url}/" >/dev/null 2>&1; then
    echo "NVR Vue UI already running at ${url}"
    echo "  ➜  Local:   ${url}/"
    sleep infinity
fi

echo "Starting NVR Vue UI at ${url}"
cd "${repo_root}/src/nvr_ui"
exec npm run dev:debug
