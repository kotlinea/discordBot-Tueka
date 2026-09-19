#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in git docker; do
  command -v "$tool" >/dev/null || { echo "$tool is required; see handbook/operator/setup.md" >&2; exit 2; }
done
setup_python="${TUEKA_SETUP_PYTHON:-python3.13}"
"$setup_python" -c 'import sys; assert sys.version_info[:2] == (3, 13), "Python 3.13 required; see handbook/operator/setup.md"'
if [ ! -x .venv-operator/bin/python ]; then "$setup_python" -m venv .venv-operator; fi
.venv-operator/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 13)'
.venv-operator/bin/python -m pip install --require-hashes -r requirements.lock
.venv-operator/bin/python scripts/setup.py "$@"
