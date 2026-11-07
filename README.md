# WAVE-CLI

```text
__      __  _____  ___      ___  _______         ______   ___       __  
\ \    / / /  _  \ \  \    /  / |   ____|       /  ____| |   |     |  | 
 \ \  / / /  /_\  \ \  \  /  /  |  |___   ____ |  |      |   |     |  | 
  \ \/ / /   ___   \ \  \/  /   |   ___| |____||  |      |   |     |  | 
   \  / /   /   \   \ \    /    |  |___        |  `----. |   `----.|  | 
    \/ /___/     \___\ \__/     |_______|       \______| |________||__| 
```

> Minimalist, Zero-Flicker, Spotify-Style Terminal Music Player for Linux.

Built with Python (**Textual** & **Rich**), **mpv** UNIX domain socket JSON IPC, and **yt-dlp**.

---

## Fitur Utama

* **Spotify-Style Two-Pane Layout:**
  * Sidebar navigasi kiri (`Search`, `Queue`, `Liked`, `History`, `Radio`, dan daftar `Playlists`).
  * Panel utama daftar lagu dengan metadata lengkap (nomor, judul, artis, cache status, durasi).
  * Player bar persisten di bagian bawah dengan scrubber ASCII dan meter volume.
* **100% Zero-Flicker Architecture:**
  * Memanfaatkan differential rendering Textual.
  * Update status playback dilakukan secara atomik setiap 250ms tanpa me-redraw tabel lagu.
* **Pure Clean ASCII Aesthetic:**
  * Desain terminal modern dan tajam tanpa emoji, cocok untuk Kitty, Alacritty, WezTerm, Foot, maupun tmux.
  * Transparansi latar belakang penuh (100% transparent glass mode).
* **Offline Audio Caching:**
  * Lagu favorit dan playlist dapat diunduh otomatis dalam format Opus (`~/.cache/wave-cli/audio/`).
  * Indikator status `[v]` warna hijau terang menandakan lagu siap diputar offline instan tanpa kuota internet.
  * Tombol `[ Download Semua ]` untuk batch caching satu playlist atau seluruh lagu Liked.
* **Import Playlist YouTube Instan:**
  * Cukup paste tautan playlist YouTube ke kotak pencarian atau tekan `I` untuk membuka modal import.
  * Pengguna dapat menentukan nama kustom sebelum playlist disimpan ke database lokal.
* **Smart Repeat & Shuffle:**
  * Mode Repeat: `OFF` -> `ALL` (loop playlist/queue) -> `ONE` (loop single track).
  * Mode Shuffle: Acak urutan pemutaran lagu saat beralih trek berikutnya.
* **Continuous Radio Mix (Autoplay):**
  * Auto-fetch radio mix YouTube saat antrean utama habis, menjaga pemutaran musik tetap berjalan tanpa henti.
* **Penyimpanan Lokal Andal (SQLite WAL):**
  * Database tersimpan aman di `~/.local/share/wave-cli/library.db` dengan proteksi foreign key cascade dan migrasi otomatis.

---

## Kebutuhan Sistem

* **Sistem Operasi:** Linux, macOS (Apple Silicon / Intel), atau Windows
* **mpv:** Audio backend dan JSON IPC engine
* **Python 3.10+:** (Hanya jika menjalankan via source code / pip; tidak diperlukan jika menggunakan Standalone Binary)
* **yt-dlp:** Ekstraksi audio streaming (diinstall otomatis oleh installer)

Instalasi `mpv`:
```bash
# Ubuntu / Debian / Linux Mint
sudo apt update && sudo apt install mpv

# Arch Linux / Manjaro
sudo pacman -S mpv

# Fedora
sudo dnf install mpv

# macOS (Homebrew)
brew install mpv

# Windows (Chocolatey atau Winget)
choco install mpv
# atau: winget install mpv.net
```

---

## Panduan Instalasi

### Metode 1: Download Standalone Binary (Tanpa Setup Python)

Anda bisa langsung mengunduh binary portabel yang sudah terkompilasi dari halaman **GitHub Releases**:

* **Linux x86_64:** `wave-linux-x86_64.tar.gz`
* **macOS Apple Silicon (M1/M2/M3/M4):** `wave-macos-arm64.tar.gz`
* **macOS Intel:** `wave-macos-x86_64.tar.gz`
* **Windows x86_64:** `wave-windows-x86_64.zip`

Cukup ekstrak file tersebut dan pindahkan ke direktori PATH Anda:
```bash
# Contoh untuk Linux / macOS:
tar -xvf wave-linux-x86_64.tar.gz
sudo mv wave /usr/local/bin/wave
```

---

### Metode 2: Skrip Otomatis Linux (Direkomendasikan dari Source)

Jalankan skrip installer yang telah disediakan di dalam repositori:

```bash
git clone https://github.com/username/wave-cli.git
cd wave-cli
./install.sh
```

Skrip ini akan secara otomatis:
1. Memeriksa keberadaan Python >= 3.10 dan `mpv`.
2. Menyiapkan environment terisolasi di `~/.local/share/wave-cli/venv`.
3. Memasang dependensi Python (`textual`, `rich`, `platformdirs`, `yt-dlp`).
4. Membuat shortcut perintah global `wave` dan `wave-cli` di `~/.local/bin/`.

*(Jika Anda ingin menghubungkan langsung ke folder repository untuk pengembangan, gunakan `./install.sh --dev`)*.

---

### Metode 2: Pipx / Pip

Jika Anda terbiasa menggunakan `pipx` atau `pip`:

```bash
cd wave-cli
pipx install .
# atau
pip install .
```

---

### Metode 3: Standalone Single-File Binary (PyInstaller)

Jika Anda ingin menghasilkan satu binary mandiri tanpa perlu dependensi Python di sistem target:

```bash
./build_binary.sh
```

Hasil kompilasi executable akan tersedia di `dist/wave`. Pindahkan binary tersebut ke direktori PATH sistem Anda:

```bash
cp dist/wave ~/.local/bin/wave
```

---

## Cara Menjalankan

Cukup ketik salah satu perintah berikut dari mana saja di terminal:

```bash
# Buka aplikasi
wave

# Buka dan langsung cari lagu atau paste link playlist:
wave "coldplay yellow"
wave "https://www.youtube.com/playlist?list=PL..."

# Bantuan dan versi:
wave --help
wave --version
```

---

## Pintasan Navigasi Keyboard

| Tombol | Aksi |
| :--- | :--- |
| `/` | Fokus ke kolom pencarian / input URL |
| `Enter` | Putar lagu yang dipilih / submit form |
| `Space` | Toggle Play / Pause |
| `p` / `n` | Putar lagu Sebelumnya (**Prev**) / Berikutnya (**Next**) |
| `h` / `l` | Mundur / Maju 5 detik (**Seek -/+ 5s**) |
| `+` / `-` | Naikkan / Turunkan volume audio |
| `f` / `F` | Toggle lagu Favorit (**Liked**) pada baris terpilih atau Now Playing |
| `s` | Toggle **Shuffle Mode** (ON / OFF) |
| `t` | Siklus **Repeat Mode** (OFF -> ALL -> ONE) |
| `r` | Toggle **Autoplay Radio** (ON / OFF) |
| `a` | Tambahkan lagu yang dipilih ke antrean (**Queue**) |
| `m` | Buka menu tambahkan lagu ke **Playlist** |
| `P` | Buat **Playlist Baru** |
| `I` | Buka modal **Import Playlist YouTube** |
| `d` | Hapus lagu atau playlist terpilih (**Delete**) |
| `C` | Bersihkan antrean (**Clear Queue**) |
| `1` | Navigasi ke tab **Search** |
| `2` | Navigasi ke tab **Queue** |
| `3` | Navigasi ke tab **Liked Songs** |
| `4` | Navigasi ke tab **History** |
| `5` | Navigasi ke tab **Radio** |
| `Esc` | Lepas fokus dari input teks kembali ke navigasi tabel |
| `q` | Tutup aplikasi dan matikan proses audio secara bersih |

---

## Lokasi Data & Cache (XDG Base Directory)

* **Database (Riwayat, Liked, Playlist):**
  `~/.local/share/wave-cli/library.db`
* **Audio Cache (Opus Native):**
  `~/.cache/wave-cli/audio/`
* **MPV Socket:**
  `/tmp/wave-cli-mpv.sock`

---

## Menghapus Instalasi (Uninstall)

Untuk menghapus instalasi `wave-cli` beserta binary command:

```bash
./install.sh --uninstall
```

Atau hapus secara manual:
```bash
rm -rf ~/.local/share/wave-cli
rm -f ~/.local/bin/wave ~/.local/bin/wave-cli
```

---

## Lisensi

Didistribusikan di bawah lisensi MIT.
