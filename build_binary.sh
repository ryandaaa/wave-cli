#!/usr/bin/env bash
# ==============================================================================
# WAVE-CLI STANDALONE BINARY BUILDER
# Builds a single-file executable using PyInstaller
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "=========================================================="
echo "          Building Standalone WAVE-CLI Binary             "
echo "=========================================================="

# Check Python environment
PY_BIN="python3"
if [ -f "${SCRIPT_DIR}/venv/bin/python" ]; then
    PY_BIN="${SCRIPT_DIR}/venv/bin/python"
elif [ -f "${SCRIPT_DIR}/.venv/bin/python" ]; then
    PY_BIN="${SCRIPT_DIR}/.venv/bin/python"
fi

echo "[INFO] Menggunakan Python: ${PY_BIN}"

# Check or install PyInstaller
if ! "${PY_BIN}" -m PyInstaller --version >/dev/null 2>&1; then
    echo "[INFO] Menginstall PyInstaller..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "${PY_BIN}" pyinstaller
    else
        "${PY_BIN}" -m pip install pyinstaller
    fi
fi

# Clean previous build artifacts
rm -rf "${SCRIPT_DIR}/build" "${SCRIPT_DIR}/dist" "${SCRIPT_DIR}/wave.spec"

echo "[INFO] Menjalankan PyInstaller..."
"${PY_BIN}" -m PyInstaller \
    --name wave \
    --onefile \
    --clean \
    --noconfirm \
    --add-data "wave.tcss:." \
    --collect-data textual \
    --collect-data rich \
    main.py

echo ""
echo "=========================================================="
echo "[OK] Binary berhasil dibuat di: ${SCRIPT_DIR}/dist/wave"
echo "Ukuran: $(du -h "${SCRIPT_DIR}/dist/wave" | cut -f1)"
echo ""
echo "Anda bisa langsung memindahkannya ke sistem PATH:"
echo "    sudo cp dist/wave /usr/local/bin/wave"
echo "    # atau"
echo "    cp dist/wave ~/.local/bin/wave"
echo "=========================================================="
