#!/usr/bin/env bash
# Start SprintOS with the local launcher from the repo root.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
python3 scripts/launch.py
