# WAVE-CLI

> Minimalist, Zero-Flicker, Spotify-Style Terminal Music Player for Linux.

Built with Python (Textual & Rich), `mpv` JSON IPC, and `yt-dlp`.

---

## Fitur Utama

* **Spotify-Style Layout:**
  * Sidebar navigasi kiri (`Search`, `Queue`, `Liked`, `History`).
  * Panel utama untuk pencarian dan tabel daftar lagu.
  * Player bar persisten di bagian bawah dengan progress bar ASCII & volume meter.
* **100% Zero-Flicker Architecture:**
  * Menggunakan sistem double-buffering dan terminal diffs Textual.
  * Hanya meng-update 3 label teks player secara atomik setiap 250ms tanpa me-redraw tabel lagu.
* **Pure Clean ASCII (No Emoji):**
  * Tampilan minimalis, tajam, dan elegan di terminal Kitty.
* **Penyimpanan Lokal & Playlist (SQLite):**
  * Fitur **Custom Playlists** dengan dialog modal transparan untuk membuat playlist dan mengelompokkan lagu.
  * Fitur **Import YouTube Playlist** otomatis dengan mem-paste link playlist YouTube langsung di kolom pencarian.
  * Lagu favorit (Liked) dan riwayat pemutaran (History) tersimpan permanen di `~/.local/share/wave-cli/library.db`.
* **Audio Engine PipeWire:**
  * Streaming audio bit-perfect Opus via `mpv` dengan integrasi kontrol dua arah via UNIX Domain Socket JSON IPC.

---

## Cara Menjalankan

Cukup ketik salah satu perintah berikut dari mana saja di terminal:

```bash
wave
# atau
wave-cli
```

---

## Navigasi Keyboard (Shortcuts)

| Tombol | Fungsi |
| :--- | :--- |
| `/` | Fokus ke kotak pencarian YouTube |
| `Enter` | Putar lagu yang dipilih (atau submit pencarian) |
| `Space` | Play / Pause toggle |
| `p` | Putar lagu sebelumnya (**Prev Track**) |
| `a` | Tambahkan lagu yang dipilih ke antrean (**Queue**) |
| `m` | Tambahkan lagu yang dipilih ke playlist (**Add to Playlist**) |
| `P` | Buat playlist baru (**New Playlist Modal**) |
| `f` | Simpan / Hapus lagu dari favorit (**Liked Songs**) |
| `d` | Hapus lagu dari Playlist/Queue saat ini (**Delete Track/PL**) |
| `n` | Lompat ke lagu berikutnya (**Next Track**) |
| `h` / `l` | Mundur / Maju 5 detik (**Seek -/+ 5s**) |
| `+` / `-` | Naikkan / Turunkan volume (**Volume +/-**) |
| `1` | Buka tab **Search** |
| `2` | Buka tab **Queue** |
| `3` | Buka tab **Liked Songs** |
| `4` | Buka tab **History** |
| `Esc` | Lepaskan fokus dari kotak pencarian kembali ke tabel |
| `q` | Keluar dari aplikasi dan hentikan musik secara bersih |
