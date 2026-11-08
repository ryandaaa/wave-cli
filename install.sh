#!/usr/bin/env bash
# ==============================================================================
# WAVE-CLI ONE-LINE AUTO INSTALLER
# Minimalist, Zero-Flicker, Spotify-Style Terminal Music Player
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ryandaaa/wave-cli/main/install.sh | bash
# ==============================================================================

set -euo pipefail

APP_NAME="wave-cli"
BIN_NAME="wave"
BIN_DIR="${HOME}/.local/bin"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wave-cli"
GITHUB_REPO="ryandaaa/wave-cli"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
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
    echo -e "${CYAN}"
    echo "=========================================================="
    echo "                 WAVE-CLI AUTO INSTALLER                  "
    echo "    Spotify-Style Zero-Flicker Music Player for Linux     "
    echo "=========================================================="
    echo -e "${NC}"
}

get_mpv_hint() {
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "brew install mpv"
        return
    fi

    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        case "${ID:-}" in
            ubuntu|debian|linuxmint|pop)
                echo "sudo apt update && sudo apt install -y mpv"
                return
                ;;
            arch|manjaro|endeavouros)
                echo "sudo pacman -S mpv"
                return
                ;;
            fedora|rhel|centos)
                echo "sudo dnf install -y mpv"
                return
                ;;
            opensuse*|suse)
                echo "sudo zypper install -y mpv"
                return
                ;;
            void)
                echo "sudo xbps-install -S mpv"
                return
                ;;
            alpine)
                echo "sudo apk add mpv"
                return
                ;;
        esac

        # Check ID_LIKE
        case "${ID_LIKE:-}" in
            *debian*|*ubuntu*)
                echo "sudo apt update && sudo apt install -y mpv"
                return
                ;;
            *arch*)
                echo "sudo pacman -S mpv"
                return
                ;;
            *fedora*|*rhel*)
                echo "sudo dnf install -y mpv"
                return
                ;;
        esac
    fi

    echo "sudo apt install mpv  # atau gunakan package manager distro Anda"
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

# Ensure bin directory exists
mkdir -p "${BIN_DIR}"

# ------------------------------------------------------------------------------
# 2. Detect OS & Architecture
# ------------------------------------------------------------------------------
log_info "Mendeteksi arsitektur sistem..."
OS_TYPE="$(uname -s)"
ARCH_TYPE="$(uname -m)"

TARGET=""
if [[ "${OS_TYPE}" == "Linux" ]]; then
    if [[ "${ARCH_TYPE}" == "x86_64" ]]; then
        TARGET="linux-x86_64"
    elif [[ "${ARCH_TYPE}" == "aarch64" || "${ARCH_TYPE}" == "arm64" ]]; then
        TARGET="linux-arm64"
    fi
elif [[ "${OS_TYPE}" == "Darwin" ]]; then
    if [[ "${ARCH_TYPE}" == "arm64" ]]; then
        TARGET="macos-arm64"
    elif [[ "${ARCH_TYPE}" == "x86_64" ]]; then
        TARGET="macos-x86_64"
    fi
fi

if [ -n "${TARGET}" ]; then
    log_success "Sistem terdeteksi: ${TARGET} (${OS_TYPE} ${ARCH_TYPE})"
else
    log_warn "Arsitektur ${OS_TYPE} ${ARCH_TYPE} belum memiliki binary rilis resmi. Akan menggunakan instalasi source."
fi

# ------------------------------------------------------------------------------
# 3. Mode Selection (Binary vs Dev vs Source)
# ------------------------------------------------------------------------------
DEV_MODE=0
SOURCE_MODE=0

if [[ "${1:-}" == "--dev" ]] || [[ "${1:-}" == "--link" ]]; then
    DEV_MODE=1
elif [[ "${1:-}" == "--source" ]] || [[ "${1:-}" == "--build" ]] || [ -z "${TARGET}" ]; then
    SOURCE_MODE=1
fi

INSTALLED_METHOD=""

# ------------------------------------------------------------------------------
# 4. Method A: Fast Standalone Binary Download (~3s)
# ------------------------------------------------------------------------------
if [ "${DEV_MODE}" -eq 0 ] && [ "${SOURCE_MODE}" -eq 0 ]; then
    ASSET_NAME="wave-${TARGET}.tar.gz"
    DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/latest/download/${ASSET_NAME}"
    
    log_info "Mengunduh standalone binary wave terbaru dari GitHub Releases..."
    
    TMP_DIR="$(mktemp -d)"
    ARCHIVE_PATH="${TMP_DIR}/${ASSET_NAME}"
    
    DOWNLOAD_SUCCESS=0
    if command -v curl >/dev/null 2>&1; then
        if curl -fsSL -o "${ARCHIVE_PATH}" "${DOWNLOAD_URL}" 2>/dev/null; then
            DOWNLOAD_SUCCESS=1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -q -O "${ARCHIVE_PATH}" "${DOWNLOAD_URL}" 2>/dev/null; then
            DOWNLOAD_SUCCESS=1
        fi
    fi

    if [ "${DOWNLOAD_SUCCESS}" -eq 1 ] && [ -f "${ARCHIVE_PATH}" ]; then
        tar -xzf "${ARCHIVE_PATH}" -C "${TMP_DIR}"
        if [ -f "${TMP_DIR}/wave" ]; then
            mv "${TMP_DIR}/wave" "${BIN_DIR}/${BIN_NAME}"
            chmod +x "${BIN_DIR}/${BIN_NAME}"
            ln -sf "${BIN_DIR}/${BIN_NAME}" "${BIN_DIR}/${APP_NAME}"
            rm -rf "${TMP_DIR}"
            log_success "Binary mandiri berhasil dipasang di ${BIN_DIR}/${BIN_NAME}."
            INSTALLED_METHOD="binary"
        fi
    fi

    if [ "${INSTALLED_METHOD}" != "binary" ]; then
        log_warn "Unduhan binary rilis gagal atau belum tersedia. Beralih ke instalasi Python..."
        SOURCE_MODE=1
        rm -rf "${TMP_DIR:-}"
    fi
fi

# ------------------------------------------------------------------------------
# 5. Method B: Source / Development Mode (Fallback)
# ------------------------------------------------------------------------------
if [ "${INSTALLED_METHOD}" != "binary" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
    
    if [ "${DEV_MODE}" -eq 1 ] && [ -n "${SCRIPT_DIR}" ] && [ -f "${SCRIPT_DIR}/main.py" ]; then
        log_info "Mode pengembangan aktif: Menghubungkan langsung ke folder repository."
        INSTALL_DIR="${SCRIPT_DIR}"
    else
        log_info "Menyiapkan instalasi source di ${INSTALL_DIR}..."
        mkdir -p "${INSTALL_DIR}"
        
        if [ -n "${SCRIPT_DIR}" ] && [ -f "${SCRIPT_DIR}/main.py" ]; then
            cp "${SCRIPT_DIR}/main.py" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/tui.py" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/player.py" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/search.py" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/database.py" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/audio_cache.py" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/wave.tcss" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/pyproject.toml" "${INSTALL_DIR}/"
            cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
        else
            log_info "Mengunduh kode sumber wave-cli dari GitHub..."
            ARCHIVE_URL="https://github.com/${GITHUB_REPO}/archive/refs/heads/main.tar.gz"
            TMP_SRC="$(mktemp -d)"
            curl -fsSL "${ARCHIVE_URL}" | tar -xz -C "${TMP_SRC}"
            cp -r "${TMP_SRC}/wave-cli-main/"* "${INSTALL_DIR}/"
            rm -rf "${TMP_SRC}"
        fi
    fi

    # Setup Virtual Environment
    VENV_DIR="${INSTALL_DIR}/venv"
    if [ ! -d "${VENV_DIR}" ]; then
        log_info "Membuat virtual environment di ${VENV_DIR}..."
        if command -v uv >/dev/null 2>&1; then
            uv venv "${VENV_DIR}"
        else
            python3 -m venv "${VENV_DIR}"
        fi
    fi

    log_info "Menginstall dependensi Python..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "${VENV_DIR}/bin/python" textual>=0.80.0 rich>=13.0.0 platformdirs>=4.0.0 yt-dlp
    else
        "${VENV_DIR}/bin/python" -m pip install --upgrade pip
        "${VENV_DIR}/bin/python" -m pip install textual>=0.80.0 rich>=13.0.0 platformdirs>=4.0.0 yt-dlp
    fi

    WRAPPER="#!/usr/bin/env bash
exec \"${VENV_DIR}/bin/python\" \"${INSTALL_DIR}/main.py\" \"\$@\"
"
    echo "${WRAPPER}" > "${BIN_DIR}/${BIN_NAME}"
    chmod +x "${BIN_DIR}/${BIN_NAME}"
    echo "${WRAPPER}" > "${BIN_DIR}/${APP_NAME}"
    chmod +x "${BIN_DIR}/${APP_NAME}"
    log_success "Script launcher berhasil dibuat di ${BIN_DIR}/${BIN_NAME}."
    INSTALLED_METHOD="source"
fi

# ------------------------------------------------------------------------------
# 6. Automatic yt-dlp Provisioning
# ------------------------------------------------------------------------------
if command -v yt-dlp >/dev/null 2>&1 || [ -x "${BIN_DIR}/yt-dlp" ]; then
    log_success "'yt-dlp' terdeteksi."
else
    log_info "'yt-dlp' belum ditemukan. Mengunduh official standalone binary..."
    YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    if curl -fsSL -o "${BIN_DIR}/yt-dlp" "${YTDLP_URL}" 2>/dev/null; then
        chmod +x "${BIN_DIR}/yt-dlp"
        log_success "'yt-dlp' berhasil dipasang otomatis ke ${BIN_DIR}/yt-dlp."
    else
        log_warn "Gagal mengunduh yt-dlp otomatis. Anda bisa menginstallnya nanti via package manager."
    fi
fi

# ------------------------------------------------------------------------------
# 7. Check mpv Dependency
# ------------------------------------------------------------------------------
if command -v mpv >/dev/null 2>&1; then
    log_success "'mpv' ditemukan: $(command -v mpv)"
else
    MPV_CMD="$(get_mpv_hint)"
    echo ""
    log_warn "'mpv' belum terpasang di sistem Anda!"
    echo -e "  wave-cli membutuhkan 'mpv' sebagai audio engine untuk memutar musik."
    echo -e "  Silakan pasang dengan menjalankan perintah:"
    echo -e "    ${BOLD}${GREEN}${MPV_CMD}${NC}"
    echo ""
fi

# ------------------------------------------------------------------------------
# 8. Check PATH Environment
# ------------------------------------------------------------------------------
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    log_warn "${BIN_DIR} belum terdaftar di variabel PATH shell Anda."
    echo "  Tambahkan baris berikut ke file konfigurasi shell Anda (~/.bashrc atau ~/.zshrc):"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# ------------------------------------------------------------------------------
# 9. Finished
# ------------------------------------------------------------------------------
echo ""
echo -e "${CYAN}==========================================================${NC}"
log_success "Instalasi selesai! Anda sekarang dapat menjalankan:"
echo ""
echo "    wave"
echo "    # atau dengan pencarian langsung:"
echo "    wave \"coldplay yellow\""
echo -e "${CYAN}==========================================================${NC}"
