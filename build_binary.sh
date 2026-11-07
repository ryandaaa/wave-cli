#!/usr/bin/env bash
# ==============================================================================
# WAVE-CLI STANDALONE BINARY BUILDER
# Wraps scripts/build_release.py with Python environment auto-detection
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PY_BIN="python3"
if [ -f "${SCRIPT_DIR}/venv/bin/python" ]; then
    PY_BIN="${SCRIPT_DIR}/venv/bin/python"
elif [ -f "${SCRIPT_DIR}/.venv/bin/python" ]; then
    PY_BIN="${SCRIPT_DIR}/.venv/bin/python"
fi

# Ensure PyInstaller is installed
if ! "${PY_BIN}" -m PyInstaller --version >/dev/null 2>&1; then
    echo "[INFO] Menginstall PyInstaller..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "${PY_BIN}" pyinstaller
    else
        "${PY_BIN}" -m pip install pyinstaller
    fi
fi

exec "${PY_BIN}" "${SCRIPT_DIR}/scripts/build_release.py" "$@"
