#!/usr/bin/env bash
# Emit the integration version for CI release metadata.
set -euo pipefail

if tag="$(git describe --tags --exact-match HEAD 2>/dev/null)"; then
  echo "${tag#v}"
  exit 0
fi

python3 - <<'PY'
import json
from pathlib import Path

manifest = Path("custom_components/bradford_white_connect/manifest.json")
print(json.loads(manifest.read_text())["version"])
PY
