#!/usr/bin/env bash
# NEXUS one-command startup (Unix)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
pip install -q -r requirements.txt
python -m nexus.run
