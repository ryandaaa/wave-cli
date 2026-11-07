#!/usr/bin/env bash
# ==============================================================================
# WAVE-CLI INSTALLER
# Minimalist, Zero-Flicker, Spotify-Style Terminal Music Player for Linux
# ==============================================================================

set -euo pipefail

APP_NAME="wave-cli"
BIN_NAME="wave"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wave-cli"
BIN_DIR="${HOME}/.local/bin"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

print_banner() {
    echo "=========================================================="
    echo "                 WAVE-CLI INSTALLER                       "
    echo "    Spotify-Style Zero-Flicker Music Player for Linux     "
    echo "=========================================================="
    echo ""
}

# ------------------------------------------------------------------------------
# 1. Uninstall Mode
# ------------------------------------------------------------------------------
if [[ "${1:-}" == "--uninstall" ]] || [[ "${1:-}" == "uninstall" ]]; then
    print_banner
    log_info "Menghapus instalasi ${APP_NAME}..."
    rm -rf "${INSTALL_DIR}"
    rm -f "${BIN_DIR}/${BIN_NAME}"
    rm -f "${BIN_DIR}/${APP_NAME}"
    log_success "${APP_NAME} berhasil dihapus dari sistem."
    exit 0
fi

print_banner

# ------------------------------------------------------------------------------
# 2. Dependency Checks (Linux, Python, mpv)
# ------------------------------------------------------------------------------
log_info "Memeriksa kebutuhan sistem..."

# Check OS
if [[ "$(uname -s)" != "Linux" ]]; then
    log_error "wave-cli saat ini dirancang untuk sistem operasi Linux."
    exit 1
fi

# Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    log_error "Python 3 tidak ditemukan. Silakan install Python 3.10 atau lebih baru."
    exit 1
fi

# Check Python version >= 3.10
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    log_error "Python versi $PY_VER terdeteksi. wave-cli membutuhkan Python >= 3.10."
    exit 1
fi
log_success "Python $PY_VER ditemukan."

# Check mpv
if ! command -v mpv >/dev/null 2>&1; then
    log_warn "'mpv' belum terinstall di sistem Anda."
    echo "  Untuk menjalankan playback audio, silakan install mpv via package manager:"
    echo "    - Debian/Ubuntu: sudo apt install mpv"
    echo "    - Arch Linux:    sudo pacman -S mpv"
    echo "    - Fedora:        sudo dnf install mpv"
    echo "    - openSUSE:      sudo zypper install mpv"
    echo ""
else
    log_success "'mpv' ditemukan: $(command -v mpv)"
fi

# ------------------------------------------------------------------------------
# 3. Locate Source Files
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_MODE=0

if [[ "${1:-}" == "--dev" ]] || [[ "${1:-}" == "--link" ]]; then
    DEV_MODE=1
    log_info "Mode pengembangan (dev mode) aktif: Menghubungkan langsung ke repo saat ini."
    INSTALL_DIR="${SCRIPT_DIR}"
fi

# ------------------------------------------------------------------------------
# 4. Copy Files (if not in dev mode)
# ------------------------------------------------------------------------------
if [ "$DEV_MODE" -eq 0 ]; then
    log_info "Memasang file ke ${INSTALL_DIR}..."
    mkdir -p "${INSTALL_DIR}"
    
    # Copy source files
    cp "${SCRIPT_DIR}/main.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/tui.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/player.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/search.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/database.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/audio_cache.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/wave.tcss" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/pyproject.toml" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
fi

# ------------------------------------------------------------------------------
# 5. Virtual Environment & Dependencies Setup
# ------------------------------------------------------------------------------
VENV_DIR="${INSTALL_DIR}/venv"

if [ ! -d "${VENV_DIR}" ]; then
    log_info "Membuat virtual environment di ${VENV_DIR}..."
    if command -v uv >/dev/null 2>&1; then
        uv venv "${VENV_DIR}"
    else
        python3 -m venv "${VENV_DIR}"
    fi
fi

log_info "Menginstall dependensi Python (textual, rich, platformdirs, yt-dlp)..."
if command -v uv >/dev/null 2>&1; then
    uv pip install --python "${VENV_DIR}/bin/python" textual>=0.80.0 rich>=13.0.0 platformdirs>=4.0.0 yt-dlp
else
    "${VENV_DIR}/bin/python" -m pip install --upgrade pip
    "${VENV_DIR}/bin/python" -m pip install textual>=0.80.0 rich>=13.0.0 platformdirs>=4.0.0 yt-dlp
fi

log_success "Dependensi berhasil diinstall."

# ------------------------------------------------------------------------------
# 6. Create Global Executable Wrappers in ~/.local/bin
# ------------------------------------------------------------------------------
mkdir -p "${BIN_DIR}"

WRAPPER_CONTENT="#!/usr/bin/env bash
# Wave-CLI global launcher
exec \"${VENV_DIR}/bin/python\" \"${INSTALL_DIR}/main.py\" \"\$@\"
"

echo "${WRAPPER_CONTENT}" > "${BIN_DIR}/${BIN_NAME}"
chmod +x "${BIN_DIR}/${BIN_NAME}"

echo "${WRAPPER_CONTENT}" > "${BIN_DIR}/${APP_NAME}"
chmod +x "${BIN_DIR}/${APP_NAME}"

log_success "Perintah global dibuat di:"
echo "  - ${BIN_DIR}/${BIN_NAME}"
echo "  - ${BIN_DIR}/${APP_NAME}"

# ------------------------------------------------------------------------------
# 7. Check PATH Environment
# ------------------------------------------------------------------------------
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    log_warn "${BIN_DIR} belum terdaftar di variabel PATH Anda."
    echo "  Tambahkan baris berikut ke ~/.bashrc atau ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# ------------------------------------------------------------------------------
# 8. Finished
# ------------------------------------------------------------------------------
echo ""
echo "=========================================================="
log_success "Instalasi selesai! Anda sekarang bisa menjalankan:"
echo ""
echo "    wave"
echo "    # atau"
echo "    wave-cli"
echo "    # atau dengan pencarian langsung:"
echo "    wave \"coldplay yellow\""
echo "=========================================================="
