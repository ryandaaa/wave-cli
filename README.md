<div align="center">

# WAVE-CLI

<p><strong>Minimalist, Zero-Flicker, Spotify-Style Terminal Music Player for Linux</strong></p>

<p>
  <a href="https://github.com/ryandaaa/wave-cli/releases"><img src="https://img.shields.io/github/v/release/ryandaaa/wave-cli?style=flat-square&color=89b4fa&label=Release" alt="Release Version"></a>
  <a href="https://github.com/ryandaaa/wave-cli/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/ryandaaa/wave-cli/ci.yml?branch=main&style=flat-square&color=a6e3a1&label=CI" alt="CI Status"></a>
  <a href="https://github.com/ryandaaa/wave-cli/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ryandaaa/wave-cli?style=flat-square&color=fab387&label=License" alt="License"></a>
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-cba6f7?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.10%2B-f38ba8?style=flat-square" alt="Python Version">
  <img src="https://img.shields.io/badge/UI-Textual%20TUI-94e2d5?style=flat-square" alt="Textual">
</p>

<p>Ditenagai oleh <strong>Textual</strong> &amp; <strong>Rich</strong>, <strong>mpv</strong> UNIX Domain Socket JSON IPC, dan <strong>yt-dlp</strong>.</p>

<br />

```bash
curl -fsSL https://raw.githubusercontent.com/ryandaaa/wave-cli/main/install.sh | bash
```

</div>

<hr />

## Ikhtisar Fitur

<table>
  <tr>
    <td width="50%">
      <h4>Spotify-Style Two-Pane Layout</h4>
      Sidebar navigasi di sisi kiri (<code>Search</code>, <code>Queue</code>, <code>Liked</code>, <code>History</code>, <code>Radio</code>, <code>Playlists</code>) serta tabel track lagu interaktif di panel utama.
    </td>
    <td width="50%">
      <h4>100% Zero-Flicker Differential Rendering</h4>
      Memanfaatkan sistem diffing Textual. Status playback diperbarui secara atomik setiap 250ms tanpa me-redraw tabel lagu atau menyebabkan layar berkedip.
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h4>Offline Audio Caching (Opus Native)</h4>
      Mengunduh audio lagu favorit dan playlist langsung ke disk lokal (<code>~/.cache/wave-cli/audio/</code>). Lagu yang sudah ter-cache ditandai indikator <code>[v]</code> hijau dan diputar instan tanpa memakan kuota.
    </td>
    <td width="50%">
      <h4>Import Playlist YouTube Instan</h4>
      Cukup paste tautan playlist YouTube ke kotak pencarian atau tekan <kbd>I</kbd>. Anda dapat menentukan nama kustom sebelum playlist disimpan ke database lokal.
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h4>Smart Repeat &amp; Shuffle</h4>
      Mendukung tiga mode repeat (<code>OFF</code> &rarr; <code>ALL</code> &rarr; <code>ONE</code>) serta pengacakan antrean (<code>Shuffle</code>) yang tersimpan permanen di database.
    </td>
    <td width="50%">
      <h4>Endless Radio Mix (Autoplay)</h4>
      Ketika antrean utama pengguna selesai diputar, sistem otomatis mengambil rekomendasi Radio Mix terkait sehingga musik tidak pernah berhenti.
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h4>Transparent Glass Mode</h4>
      Mendukung 100% latar belakang transparan murni tanpa lapisan warna hitam built-in terminal (ideal untuk Kitty, WezTerm, Alacritty, dan Foot).
    </td>
    <td width="50%">
      <h4>Penyimpanan Database Andal (SQLite WAL)</h4>
      Riwayat pemutaran, antrean persisten, dan playlist disimpan rapi di <code>~/.local/share/wave-cli/library.db</code> dengan proteksi transaksi WAL mode.
    </td>
  </tr>
</table>

<hr />

## Kebutuhan Sistem

Satu-satunya dependensi eksternal yang dibutuhkan di sistem Anda adalah **`mpv`**. Komponen lainnya (termasuk `yt-dlp`) akan diurus secara otomatis oleh installer.

<table>
  <thead>
    <tr>
      <th align="left">Sistem Operasi / Distro</th>
      <th align="left">Perintah Instalasi mpv</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Ubuntu / Debian / Linux Mint / Pop!_OS</strong></td>
      <td><code>sudo apt update &amp;&amp; sudo apt install -y mpv</code></td>
    </tr>
    <tr>
      <td><strong>Arch Linux / Manjaro / EndeavourOS</strong></td>
      <td><code>sudo pacman -S mpv</code></td>
    </tr>
    <tr>
      <td><strong>Fedora / RHEL / CentOS</strong></td>
      <td><code>sudo dnf install -y mpv</code></td>
    </tr>
    <tr>
      <td><strong>openSUSE</strong></td>
      <td><code>sudo zypper install -y mpv</code></td>
    </tr>
    <tr>
      <td><strong>macOS (Homebrew)</strong></td>
      <td><code>brew install mpv</code></td>
    </tr>
    <tr>
      <td><strong>Windows (Winget / Chocolatey)</strong></td>
      <td><code>winget install mpv.net</code> <em>atau</em> <code>choco install mpv</code></td>
    </tr>
  </tbody>
</table>

<hr />

## Panduan Instalasi

### Metode 1: Satu Baris Auto-Install (Direkomendasikan)

Salin dan jalankan perintah berikut di terminal Linux atau macOS Anda:

```bash
curl -fsSL https://raw.githubusercontent.com/ryandaaa/wave-cli/main/install.sh | bash
```

> [!NOTE]
> Skrip ini secara otomatis mendeteksi arsitektur sistem Anda (`Linux x86_64` atau `macOS arm64`), mengunduh binary standalone yang siap pakai ke `~/.local/bin/wave`, dan otomatis memasang `yt-dlp` jika belum tersedia. Tidak membutuhkan Python atau hak akses root/sudo.

<details>
<summary><strong>Metode 2: Download Manual dari GitHub Releases</strong></summary>
<br />

Anda dapat langsung mengambil binary hasil kompilasi resmi dari halaman <a href="https://github.com/ryandaaa/wave-cli/releases/latest"><strong>GitHub Releases</strong></a>:

* **Linux x86_64:** `wave-linux-x86_64.tar.gz`
* **macOS Apple Silicon:** `wave-macos-arm64.tar.gz`
* **Windows x86_64:** `wave-windows-x86_64.zip`

Ekstrak dan pindahkan binary ke direktori PATH Anda:
```bash
# Contoh untuk Linux / macOS:
tar -xvf wave-linux-x86_64.tar.gz
sudo mv wave /usr/local/bin/wave
```
</details>

<details>
<summary><strong>Metode 3: Instalasi dari Source Code (Git Clone &amp; Dev Mode)</strong></summary>
<br />

Jika Anda ingin memodifikasi atau mengembangkan `wave-cli` secara lokal:

```bash
git clone https://github.com/ryandaaa/wave-cli.git
cd wave-cli
./install.sh --dev
```

Atau menggunakan `pipx` / `pip`:
```bash
pipx install .
# atau:
pip install .
```
</details>

<details>
<summary><strong>Metode 4: Kompilasi Standalone Binary Sendiri (PyInstaller)</strong></summary>
<br />

Jika Anda ingin membuat binary tunggal mandiri dari source code:

```bash
./build_binary.sh
```
Binary hasil kompilasi akan berada di folder `dist/wave`.
</details>

<hr />

## Cara Menjalankan

Setelah terpasang, cukup ketik perintah `wave` dari mana saja di terminal:

```bash
# Membuka antarmuka TUI wave-cli
wave

# Membuka dan langsung mencari lagu
wave "coldplay yellow"

# Membuka dan langsung mengimpor playlist YouTube
wave "https://www.youtube.com/playlist?list=PL..."

# Bantuan dan informasi versi
wave --help
wave --version
```

<hr />

## Pintasan Navigasi Keyboard

<table>
  <thead>
    <tr>
      <th align="center">Tombol</th>
      <th align="left">Aksi</th>
      <th align="left">Kategori</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td align="center"><kbd>/</kbd></td>
      <td>Fokus ke kolom pencarian atau input tautan YouTube</td>
      <td>Pencarian</td>
    </tr>
    <tr>
      <td align="center"><kbd>Esc</kbd></td>
      <td>Lepas fokus dari input teks kembali ke navigasi tabel lagu</td>
      <td>Pencarian</td>
    </tr>
    <tr>
      <td align="center"><kbd>Enter</kbd></td>
      <td>Putar lagu yang dipilih atau submit pencarian/formulir</td>
      <td>Playback</td>
    </tr>
    <tr>
      <td align="center"><kbd>Space</kbd></td>
      <td>Toggle Play / Pause</td>
      <td>Playback</td>
    </tr>
    <tr>
      <td align="center"><kbd>p</kbd> / <kbd>n</kbd></td>
      <td>Putar lagu Sebelumnya (<strong>Previous</strong>) / Berikutnya (<strong>Next</strong>)</td>
      <td>Playback</td>
    </tr>
    <tr>
      <td align="center"><kbd>h</kbd> / <kbd>l</kbd></td>
      <td>Mundur / Maju 5 detik (<strong>Seek -/+ 5s</strong>)</td>
      <td>Playback</td>
    </tr>
    <tr>
      <td align="center"><kbd>+</kbd> / <kbd>-</kbd></td>
      <td>Naikkan / Turunkan volume audio</td>
      <td>Playback</td>
    </tr>
    <tr>
      <td align="center"><kbd>s</kbd></td>
      <td>Toggle <strong>Shuffle Mode</strong> (Acak urutan lagu)</td>
      <td>Mode</td>
    </tr>
    <tr>
      <td align="center"><kbd>t</kbd></td>
      <td>Siklus <strong>Repeat Mode</strong> (<code>OFF</code> &rarr; <code>ALL</code> &rarr; <code>ONE</code>)</td>
      <td>Mode</td>
    </tr>
    <tr>
      <td align="center"><kbd>r</kbd></td>
      <td>Toggle <strong>Autoplay Radio</strong> (Rekomendasi otomatis saat antrean habis)</td>
      <td>Mode</td>
    </tr>
    <tr>
      <td align="center"><kbd>f</kbd> / <kbd>F</kbd></td>
      <td>Simpan / Hapus lagu dari favorit (<strong>Liked Songs</strong>)</td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>a</kbd></td>
      <td>Tambahkan lagu yang dipilih ke antrean pemutaran (<strong>Queue</strong>)</td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>m</kbd></td>
      <td>Buka menu pop-up untuk menambahkan lagu ke <strong>Playlist</strong></td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>P</kbd></td>
      <td>Buka modal dialog untuk membuat <strong>Playlist Baru</strong></td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>I</kbd></td>
      <td>Buka modal dialog untuk <strong>Import Playlist YouTube</strong></td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>d</kbd> / <kbd>Delete</kbd></td>
      <td>Hapus lagu dari Playlist/Queue aktif, atau hapus playlist terpilih</td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>C</kbd></td>
      <td>Bersihkan seluruh daftar antrean (<strong>Clear Queue</strong>)</td>
      <td>Koleksi</td>
    </tr>
    <tr>
      <td align="center"><kbd>1</kbd> s/d <kbd>5</kbd></td>
      <td>Pindah cepat tab navigasi (<code>1: Search</code>, <code>2: Queue</code>, <code>3: Liked</code>, <code>4: History</code>, <code>5: Radio</code>)</td>
      <td>Navigasi</td>
    </tr>
    <tr>
      <td align="center"><kbd>q</kbd></td>
      <td>Keluar dari aplikasi dan matikan engine pemutar audio secara bersih</td>
      <td>Sistem</td>
    </tr>
  </tbody>
</table>

<hr />

## Lokasi Data & Direktori Cache

Aplikasi mengikuti spesifikasi **XDG Base Directory**:

<table>
  <thead>
    <tr>
      <th align="left">Komponen</th>
      <th align="left">Lokasi File di Sistem</th>
      <th align="left">Keterangan</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Database Perpustakaan</strong></td>
      <td><code>~/.local/share/wave-cli/library.db</code></td>
      <td>Menyimpan riwayat pemutaran, lagu favorit (Liked), dan daftar playlist (SQLite WAL).</td>
    </tr>
    <tr>
      <td><strong>Cache Audio Offline</strong></td>
      <td><code>~/.cache/wave-cli/audio/&lt;video_id&gt;.opus</code></td>
      <td>File audio mentah hasil unduhan untuk pemutaran tanpa kuota internet.</td>
    </tr>
    <tr>
      <td><strong>UNIX IPC Socket</strong></td>
      <td><code>/tmp/wave-mpv-&lt;pid&gt;.sock</code></td>
      <td>Koneksi komunikasi dua arah antara antarmuka Textual dan engine mpv.</td>
    </tr>
  </tbody>
</table>

<hr />

## Struktur Project

```
wave/
├── cli.py             # CLI entrypoint, argument parsing, dan bootstrap aplikasi
├── paths.py           # Sentralisasi path file sistem (cache, db, mpv IPC socket)
├── db/                # Layer database SQLite WAL (koleksi, riwayat, antrean, state)
├── player/            # Controller playback mpv engine via UNIX domain socket JSON IPC
├── youtube/           # Integrasi yt-dlp (pencarian, playlist, radio mix)
├── cache/             # Manajemen offline audio cache (unduh, ukuran, rotasi)
├── util/              # Utilitas format durasi, ASCII progress bar, volume bar
└── tui/               # Textual TUI (app core, mixins, modal dialog, custom widgets, tcss)
```

<hr />

## Menghapus Instalasi (Uninstall)

<details>
<summary><strong>Petunjuk Menghapus Instalasi</strong></summary>
<br />

Jika Anda menggunakan skrip auto-installer:
```bash
./install.sh --uninstall
```

Atau hapus secara manual dari sistem Anda:
```bash
rm -f ~/.local/bin/wave ~/.local/bin/wave-cli
rm -rf ~/.local/share/wave-cli
```
</details>

<hr />

<div align="center">
  <p>Didistribusikan di bawah <a href="LICENSE"><strong>MIT License</strong></a>.</p>
</div>
