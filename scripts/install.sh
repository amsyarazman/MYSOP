#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if command -v python3 >/dev/null 2>&1; then
  mysop_python=python3
elif command -v python >/dev/null 2>&1; then
  mysop_python=python
else
  echo "Install Python 3.12 or newer, then run this script again." >&2
  exit 1
fi
"$mysop_python" -c 'import sys; sys.exit("MYSOP requires Python 3.12 or newer.") if sys.version_info < (3, 12) else None'
"$mysop_python" -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.lock
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
