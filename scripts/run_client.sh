#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname "$SCRIPT_DIR")
cd "$REPO_ROOT"

PYTHON=${PYTHON:-python3}
if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
fi

exec "$PYTHON" -m client.webrtc_client --cli "$@"

