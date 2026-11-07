"""
Wave-CLI: Spotify-Style Terminal Music Player (Textual TUI)
Clean ASCII, 100% Zero-Flicker Architecture
"""

import asyncio
import random
from typing import Dict, List, Optional
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.events import Click
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static
from textual.content import Content
from textual import on, work

from pathlib import Path
from database import Database
from player import Player
from search import search_youtube, format_duration, is_playlist_url, fetch_youtube_playlist, fetch_radio_mix
from audio_cache import is_track_cached, download_track_audio

from textual.renderables import blank
from textual.color import Color
from rich.style import Style as RichStyle
from textual import style

# ---------------- ROOT TRANSPARENCY PATCH ----------------
# 1. Intercept Textual's Blank renderer so transparent containers never emit black (#000000)
_orig_blank_init = blank.Blank.__init__

def _patched_blank_init(self, color="transparent"):
    if isinstance(color, str):
        c = Color.parse(color)
    elif isinstance(color, Color):
        c = color
    else:
        c = Color(0, 0, 0, a=0)

    if c.a == 0 or getattr(c, "is_transparent", False):
        self._rich_style = RichStyle()  # Pure transparent! No background ANSI code!
    else:
        _orig_blank_init(self, color)

blank.Blank.__init__ = _patched_blank_init

# 2. Intercept Style.__init__ so any transparent background (alpha=0) becomes None
# This prevents Textual from converting transparent Color(0,0,0,0) into Rich '#000000' on labels & text!
_orig_style_init = style.Style.__init__

def _patched_style_init(self, *args, **kwargs):
    args = list(args)
    if args:
        bg = args[0]
        if bg is not None and getattr(bg, "a", 1.0) == 0:
            args[0] = None
    elif "background" in kwargs:
        bg = kwargs["background"]
        if bg is not None and getattr(bg, "a", 1.0) == 0:
            kwargs["background"] = None
    _orig_style_init(self, *args, **kwargs)

style.Style.__init__ = _patched_style_init
# ---------------------------------------------------------


def make_progress_bar(percent: float, width: int = 32) -> str:
    """Generate fluid ASCII progress bar without emojis."""
    percent = max(0.0, min(100.0, percent))
    filled = int((percent / 100.0) * width)
    if filled >= width:
        bar = "=" * width
    elif filled > 0:
        bar = "=" * (filled - 1) + ">" + "-" * (width - filled)
    else:
        bar = "-" * width
    return f"[{bar}]"


def make_vol_bar(vol: float, width: int = 10) -> str:
    """Generate ASCII volume bar."""
    vol = max(0.0, min(100.0, vol))
    filled = int((vol / 100.0) * width)
    return "[" + "|" * filled + "." * (width - filled) + f"] {int(vol)}%"


# ---------------- SPOTIFY-STYLE TRACK ROW ----------------

class TrackRow(Horizontal):
    def __init__(self, idx: int, track: dict, is_selected: bool = False, is_playing: bool = False, is_liked: bool = False, is_radio: bool = False):
        classes = "track-row"
        if is_selected:
            classes += " row-selected"
        if is_playing:
            classes += " row-playing"
        if is_radio:
            classes += " row-radio"
        super().__init__(classes=classes, id=f"row-{idx}")
        self.idx = idx
        self.track = track
        self.is_liked = is_liked
        self.is_playing = is_playing
        self.is_radio = is_radio

    def compose(self) -> ComposeResult:
        if self.is_radio:
            yield Label(" ~R", classes="row-num", markup=False)
        else:
            yield Label(f"{self.idx + 1:02d}", classes="row-num", markup=False)
        play_lbl = Content("[ || ]") if self.is_playing else Content("[ > ]")
        yield Button(play_lbl, id=f"btn-row-play-{self.idx}", classes="row-play-btn")
        
        # Combined title & artist in a single flat label for max compactness & zero lag
        title = self.track.get("title", "Unknown Title")
        artist = self.track.get("artist")
        if artist and artist != "Unknown Artist" and artist not in title:
            title_text = f"{title} - {artist}"
        else:
            title_text = title
        yield Label(title_text, classes="row-title", markup=False)

        yield Button(Content("[ +Next ]"), id=f"btn-row-next-{self.idx}", classes="row-action-btn")
        yield Button(Content("[ +Q ]"), id=f"btn-row-q-{self.idx}", classes="row-action-btn")
        yield Button(Content("[ +PL ]"), id=f"btn-row-pl-{self.idx}", classes="row-action-btn")
        fav_lbl = Content("[ Liked ]") if self.is_liked else Content("[ Fav ]")
        fav_cls = "row-action-btn row-fav-btn" + (" is-liked" if self.is_liked else "")
        yield Button(fav_lbl, id=f"btn-row-fav-{self.idx}", classes=fav_cls)

        is_cached = is_track_cached(self.track.get("id", ""))
        cache_lbl = "[v]" if is_cached else "   "
        cache_cls = "row-cache-indicator" + (" is-cached" if is_cached else "")
        yield Label(cache_lbl, id=f"lbl-row-cache-{self.idx}", classes=cache_cls, markup=False)

        dur = self.track.get("duration", "--:--")
        yield Label(dur, classes="row-duration", markup=False)


# ---------------- MODAL SCREENS (100% TRANSPARENT) ----------------

class NewPlaylistModal(ModalScreen[Optional[str]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            with Horizontal(classes="modal-header"):
                yield Label("[BUAT PLAYLIST BARU]", id="modal-title", markup=False)
                yield Button(Content("[ x ]"), id="btn-modal-close", classes="modal-close-btn")
            yield Input(placeholder="Ketik nama playlist dan tekan Enter...", id="new-pl-input")
            with Horizontal(id="modal-btn-row"):
                yield Button(Content("[ Simpan ]"), id="btn-pl-save", classes="modal-btn")
                yield Button(Content("[ Batal ]"), id="btn-pl-cancel", classes="modal-btn")

    def on_mount(self):
        self.query_one("#new-pl-input", Input).focus()

    @on(Button.Pressed, "#btn-modal-close")
    def on_close(self):
        self.dismiss(None)

    @on(Button.Pressed, "#btn-pl-save")
    def on_save(self):
        val = self.query_one("#new-pl-input", Input).value.strip()
        self.dismiss(val if val else None)

    @on(Button.Pressed, "#btn-pl-cancel")
    def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#new-pl-input")
    def on_submit(self, event: Input.Submitted):
        val = event.value.strip()
        self.dismiss(val if val else None)

    def action_cancel(self):
        self.dismiss(None)


class PlaylistSelectModal(ModalScreen[Optional[int]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, track: dict, playlists: list):
        super().__init__()
        self.track = track
        self.playlists = playlists

    def compose(self) -> ComposeResult:
        title = self.track.get("title", "")[:32]
        with Vertical(id="modal-dialog-select"):
            with Horizontal(classes="modal-header"):
                yield Label("[TAMBAHKAN KE PLAYLIST]", id="modal-title", markup=False)
                yield Button(Content("[ x ]"), id="btn-modal-close-select", classes="modal-close-btn")
            yield Label(f"Lagu: {title}", id="modal-subtitle", markup=False)
            yield Button(Content("[+] Buat Playlist Baru"), id="btn-create-new-pl", classes="pl-select-btn pl-create-btn")
            with VerticalScroll(id="pl-scroll-list"):
                if not self.playlists:
                    yield Label("  (Belum ada playlist tersimpan)", markup=False)
                else:
                    for pl in self.playlists:
                        yield Button(Content(f"  * {pl['name']} ({pl['count']} lagu)"), id=f"pl-opt-{pl['id']}", classes="pl-select-btn")
            yield Button(Content("[ Batal ]"), id="btn-cancel-select", classes="modal-btn")

    def on_mount(self):
        btn = self.query_one("#btn-create-new-pl", Button)
        btn.focus()

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if btn_id in ("btn-cancel-select", "btn-modal-close-select"):
            self.dismiss(None)
        elif btn_id == "btn-create-new-pl":
            self.dismiss(-1)
        elif btn_id.startswith("pl-opt-"):
            pl_id = int(btn_id.replace("pl-opt-", ""))
            self.dismiss(pl_id)

    def action_cancel(self):
        self.dismiss(None)


class RenamePlaylistModal(ModalScreen[Optional[str]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, current_name: str):
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            with Horizontal(classes="modal-header"):
                yield Label("[UBAH NAMA PLAYLIST]", id="modal-title", markup=False)
                yield Button(Content("[ x ]"), id="btn-modal-close", classes="modal-close-btn")
            yield Input(value=self.current_name, placeholder="Nama baru playlist...", id="rename-pl-input")
            with Horizontal(id="modal-btn-row"):
                yield Button(Content("[ Simpan ]"), id="btn-pl-save", classes="modal-btn")
                yield Button(Content("[ Batal ]"), id="btn-pl-cancel", classes="modal-btn")

    def on_mount(self):
        self.query_one("#rename-pl-input", Input).focus()

    @on(Button.Pressed, "#btn-modal-close")
    def on_close(self):
        self.dismiss(None)

    @on(Button.Pressed, "#btn-pl-save")
    def on_save(self):
        val = self.query_one("#rename-pl-input", Input).value.strip()
        self.dismiss(val if val else None)

    @on(Button.Pressed, "#btn-pl-cancel")
    def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#rename-pl-input")
    def on_submit(self, event: Input.Submitted):
        val = event.value.strip()
        self.dismiss(val if val else None)

    def action_cancel(self):
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, title: str, message: str):
        super().__init__()
        self.dialog_title = title
        self.dialog_message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            with Horizontal(classes="modal-header"):
                yield Label(f"[{self.dialog_title}]", id="modal-title", markup=False)
                yield Button(Content("[ x ]"), id="btn-modal-close", classes="modal-close-btn")
            yield Label(self.dialog_message, id="modal-confirm-msg", markup=False)
            with Horizontal(id="modal-btn-row"):
                yield Button(Content("[ Ya, Lanjutkan ]"), id="btn-confirm-yes", classes="modal-btn modal-btn-danger")
                yield Button(Content("[ Batal ]"), id="btn-confirm-no", classes="modal-btn")

    def on_mount(self):
        self.query_one("#btn-confirm-no", Button).focus()

    @on(Button.Pressed, "#btn-modal-close")
    def on_close(self):
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm-yes")
    def on_yes(self):
        self.dismiss(True)

    @on(Button.Pressed, "#btn-confirm-no")
    def on_no(self):
        self.dismiss(False)

    def action_cancel(self):
        self.dismiss(False)


class ImportPlaylistModal(ModalScreen[Optional[Dict[str, str]]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, initial_url: str = "", default_name: str = ""):
        super().__init__()
        self.initial_url = initial_url
        self.default_name = default_name

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog-import"):
            with Horizontal(classes="modal-header"):
                yield Label("[IMPORT PLAYLIST YOUTUBE]", id="modal-title", markup=False)
                yield Button(Content("[ x ]"), id="btn-modal-close", classes="modal-close-btn")
            yield Label("Link Playlist YouTube (URL):", classes="modal-field-title", markup=False)
            yield Input(value=self.initial_url, placeholder="Paste link playlist YouTube di sini...", id="import-pl-url")
            yield Label("Nama Playlist (opsional, kosongkan untuk nama asli):", classes="modal-field-title", markup=False)
            yield Input(value=self.default_name, placeholder="Ketik nama playlist di sini...", id="import-pl-name")
            with Horizontal(id="modal-btn-row"):
                yield Button(Content("[ Simpan & Import ]"), id="btn-import-save", classes="modal-btn")
                yield Button(Content("[ Batal ]"), id="btn-import-cancel", classes="modal-btn")

    def on_mount(self):
        if self.initial_url:
            self.query_one("#import-pl-name", Input).focus()
        else:
            self.query_one("#import-pl-url", Input).focus()

    @on(Button.Pressed, "#btn-modal-close")
    def on_close(self):
        self.dismiss(None)

    @on(Button.Pressed, "#btn-import-save")
    def on_save(self):
        url = self.query_one("#import-pl-url", Input).value.strip()
        name = self.query_one("#import-pl-name", Input).value.strip()
        if not url:
            self.dismiss(None)
        else:
            self.dismiss({"url": url, "name": name})

    @on(Button.Pressed, "#btn-import-cancel")
    def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted)
    def on_submit(self, event: Input.Submitted):
        if event.input.id == "import-pl-url":
            self.query_one("#import-pl-name", Input).focus()
        else:
            self.on_save()

    def action_cancel(self):
        self.dismiss(None)


class WaveApp(App):
    CSS_PATH = Path(__file__).parent / "wave.tcss"
    TITLE = "WAVE-CLI"

    BINDINGS = [
        Binding("q", "quit_app", "Quit", show=False),
        Binding("slash", "focus_search", "Search", show=False),
        Binding("space", "toggle_pause", "Play/Pause", show=False),
        Binding("enter", "play_selected", "Play Selected", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("K", "move_track_up", "Move Up", show=False),
        Binding("J", "move_track_down", "Move Down", show=False),
        Binding("left_square_bracket", "move_track_up", "Move Up", show=False),
        Binding("right_square_bracket", "move_track_down", "Move Down", show=False),
        Binding("a", "add_queue", "Queue", show=False),
        Binding("e", "play_next_item", "Play Next", show=False),
        Binding("R", "toggle_autoplay", "Toggle Radio", show=False),
        Binding("s", "toggle_shuffle", "Toggle Shuffle", show=False),
        Binding("t", "toggle_repeat", "Toggle Repeat", show=False),
        Binding("f", "toggle_like", "Like", show=False),
        Binding("F", "toggle_like_now_playing", "Like Now Playing", show=False),
        Binding("m", "open_playlist_menu", "Add to Playlist", show=False),
        Binding("P", "create_new_playlist", "New Playlist", show=False),
        Binding("I", "import_playlist", "Import Playlist", show=False),
        Binding("r", "rename_current_playlist", "Rename Playlist", show=False),
        Binding("d", "delete_item", "Delete", show=False),
        Binding("delete", "delete_item", "Delete", show=False),
        Binding("C", "clear_current_view", "Clear", show=False),
        Binding("p", "prev_track", "Prev Track", show=False),
        Binding("n", "next_track", "Next Track", show=False),
        Binding("equal", "vol_up", "Vol +", show=False),
        Binding("plus", "vol_up", "Vol +", show=False),
        Binding("minus", "vol_down", "Vol -", show=False),
        Binding("h", "seek_backward", "Seek -5s", show=False),
        Binding("l", "seek_forward", "Seek +5s", show=False),
        Binding("1", "nav_search", "Nav Search", show=False),
        Binding("2", "nav_queue", "Nav Queue", show=False),
        Binding("3", "nav_liked", "Nav Liked", show=False),
        Binding("4", "nav_history", "Nav History", show=False),
        Binding("5", "nav_radio", "Nav Radio", show=False),
        Binding("escape", "escape_focus", "Escape", show=False),
    ]

    def __init__(self, initial_query: str = ""):
        super().__init__()
        self.initial_query = initial_query
        self.db = Database()
        state = self.db.get_player_state()
        saved_vol = float(state.get("volume", 80.0))
        saved_auto = bool(state.get("autoplay", True))
        saved_repeat = str(state.get("repeat_mode", "OFF"))
        saved_shuffle = bool(state.get("shuffle", False))
        self.player = Player(
            volume=saved_vol,
            autoplay=saved_auto,
            repeat_mode=saved_repeat,
            shuffle=saved_shuffle
        )
        self.current_view = "SEARCH"  # SEARCH, QUEUE, LIKED, HISTORY, PLAYLIST:<id>
        self.tracks_in_table: List[Dict] = []
        self.selected_idx: int = 0
        self._playback_timer = None
        # Loading and animation states
        self.is_loading_track: bool = False
        self.loading_track_info: Optional[Dict] = None
        self._load_symbol_idx: int = 0
        self._search_spinner_idx: int = 0
        self._search_spinner_timer = None
        self._current_search_query: str = ""
        self._spinner_frames = ["[ | ]", "[ / ]", "[ - ]", "[ \\ ]"]
        self._load_frames = ["|", "/", "-", "\\"]

    def render(self):
        """Render transparent background for terminal blur/transparency."""
        return blank.Blank("transparent")

    def compose(self) -> ComposeResult:
        # Top Bar
        yield Horizontal(
            Label(" [WAVE-CLI]  Spotify-Style Terminal Player", id="top-title", markup=False),
            Label("[q: Quit  /: Search  Space: Pause  1-5: Nav] ", id="top-right", markup=False),
            id="top-bar"
        )

        # Main Body (Sidebar + Content)
        with Horizontal(id="body-container"):
            # Sidebar
            with Vertical(id="sidebar"):
                yield Label("WAVE-CLI", classes="sidebar-heading", id="sidebar-brand", markup=False)
                yield Label("───────────────────────", classes="sidebar-divider", markup=False)
                yield Button("> 1. SEARCH", id="nav-btn-1", classes="nav-button nav-active")
                yield Button("  2. QUEUE (0)", id="nav-btn-2", classes="nav-button")
                yield Button("  3. LIKED (0)", id="nav-btn-3", classes="nav-button")
                yield Button("  4. HISTORY", id="nav-btn-4", classes="nav-button")
                yield Button("  5. RADIO (0)", id="nav-btn-5", classes="nav-button")

                yield Label("PLAYLISTS", classes="sidebar-heading", markup=False)
                yield Label("───────────────────────", classes="sidebar-divider", markup=False)
                yield Button("[+] Buat Playlist", id="btn-sidebar-new-pl", classes="pl-add-button")
                yield Button("[+] Import Playlist", id="btn-sidebar-import-pl", classes="pl-add-button")
                yield Vertical(id="sidebar-playlists")

                yield Label("KONTROL", classes="shortcuts-title", markup=False)
                yield Label("───────────────────────", classes="sidebar-divider", markup=False)
                yield Label("[/]     Cari / URL", classes="shortcut-text", markup=False)
                yield Label("[Enter] Putar Lagu", classes="shortcut-text", markup=False)
                yield Label("[e]     Play Next", classes="shortcut-text", markup=False)
                yield Label("[a]     Masuk Queue", classes="shortcut-text", markup=False)
                yield Label("[R]     Toggle Radio", classes="shortcut-text", markup=False)
                yield Label("[m]     Masuk Playlist", classes="shortcut-text", markup=False)
                yield Label("[P]     Playlist Baru", classes="shortcut-text", markup=False)
                yield Label("[I]     Import Playlist", classes="shortcut-text", markup=False)
                yield Label("[r]     Ubah Nama PL", classes="shortcut-text", markup=False)
                yield Label("[d]     Hapus Lagu/PL", classes="shortcut-text", markup=False)
                yield Label("[C]     Kosongkan List", classes="shortcut-text", markup=False)
                yield Label("[[ / ]] Pindah Urutan", classes="shortcut-text", markup=False)
                yield Label("[f]     Fav Lagu", classes="shortcut-text", markup=False)
                yield Label("[F]     Fav Now Playing", classes="shortcut-text", markup=False)
                yield Label("[s]     Toggle Shuffle", classes="shortcut-text", markup=False)
                yield Label("[t]     Toggle Repeat", classes="shortcut-text", markup=False)
                yield Label("[Space] Play/Pause", classes="shortcut-text", markup=False)
                yield Label("[p / n] Prev / Next", classes="shortcut-text", markup=False)
                yield Label("[h / l] Seek -/+ 5s", classes="shortcut-text", markup=False)
                yield Label("[+ / -] Volume", classes="shortcut-text", markup=False)
                yield Label("[q]     Keluar", classes="shortcut-text", markup=False)

            # Main View
            with Vertical(id="main-content"):
                with Horizontal(id="view-header"):
                    yield Label("[CARI LAGU YOUTUBE]", id="view-title", markup=False)
                    yield Horizontal(id="view-actions")
                yield Input(placeholder="Ketik judul lagu / artis atau paste link playlist YouTube...", id="search-input")
                yield Label("Tekan '/' untuk pencarian/URL playlist, atau [1-4] untuk navigasi.", id="search-status", markup=False)
                yield VerticalScroll(id="tracks-scroll")

        # Bottom Player Bar
        with Vertical(id="player-bar"):
            yield Label("[IDLE] Belum ada lagu yang diputar", id="player-title", markup=False)
            yield Label("00:00 [--------------------------------] 00:00", id="player-progress", markup=False)
            with Horizontal(id="player-controls"):
                yield Button("[|<]", id="btn-prev", classes="player-btn")
                yield Button("[>]", id="btn-play", classes="player-btn")
                yield Button("[>|]", id="btn-next", classes="player-btn")
                yield Button("[-5s]", id="btn-seek-back", classes="player-btn")
                yield Button("[+5s]", id="btn-seek-fwd", classes="player-btn")
                yield Button("[-Vol]", id="btn-vol-down", classes="player-btn")
                yield Button("[+Vol]", id="btn-vol-up", classes="player-btn")
                yield Button("[Fav]", id="btn-player-fav", classes="player-btn")
                shuf_lbl = "[Shuf:ON]" if self.player.shuffle else "[Shuf:OFF]"
                shuf_cls = "player-btn is-active" if self.player.shuffle else "player-btn"
                yield Button(shuf_lbl, id="btn-toggle-shuffle", classes=shuf_cls)
                rep_lbl = f"[Rep:{self.player.repeat_mode}]"
                rep_cls = "player-btn" + (" is-one" if self.player.repeat_mode == "ONE" else (" is-active" if self.player.repeat_mode == "ALL" else ""))
                yield Button(rep_lbl, id="btn-toggle-repeat", classes=rep_cls)
                auto_lbl = "[Radio:ON]" if self.player.autoplay else "[Radio:OFF]"
                yield Button(auto_lbl, id="btn-toggle-autoplay", classes="player-btn")
            init_vol = make_vol_bar(self.player.volume)
            yield Label(f"STATUS: Ready                    VOL: {init_vol}", id="player-status", markup=False)

    def on_mount(self):
        """Initialize mpv, track list, and periodic update timer."""
        self.player.start()
        # Restore persistent queue from database
        try:
            saved_queue = self.db.get_queue()
            if saved_queue:
                self.player.queue = list(saved_queue)
        except Exception:
            pass
        self._update_sidebar_counts()
        self._refresh_playlists_sidebar()
        self._populate_table([])
        self._playback_timer = self.set_interval(0.25, self.tick_playback)
        inp = self.query_one("#search-input", Input)
        if self.initial_query:
            inp.value = self.initial_query
            self.search_and_populate(self.initial_query)
        inp.focus()

    def _update_sidebar_counts(self):
        try:
            liked_count = len(self.db.get_liked_songs())
            queue_count = len(self.player.queue)
            radio_count = len(self.player.radio_queue)
            nav_names = [
                "SEARCH",
                f"QUEUE ({queue_count})",
                f"LIKED ({liked_count})",
                "HISTORY",
                f"RADIO ({radio_count})"
            ]
            for i, name in enumerate(nav_names, 1):
                btn = self.query_one(f"#nav-btn-{i}", Button)
                prefix = "> " if btn.has_class("nav-active") else "  "
                btn.label = f"{prefix}{i}. {name}"
        except Exception:
            pass

    def _refresh_playlists_sidebar(self):
        self._update_playlists_sidebar()

    @work(exclusive=True, group="sidebar", thread=False)
    async def _update_playlists_sidebar(self):
        try:
            pl_container = self.query_one("#sidebar-playlists", Vertical)
            await pl_container.remove_children()
            playlists = self.db.get_playlists()
            if playlists:
                btns = []
                for pl in playlists:
                    is_active = self.current_view == f"PLAYLIST:{pl['id']}"
                    prefix = "> " if is_active else "  "
                    name = pl['name']
                    if len(name) > 13:
                        name = name[:11] + ".."
                    btn_lbl = f"{prefix}* {name} ({pl['count']})"
                    btn_classes = "nav-button nav-active" if is_active else "nav-button"
                    btns.append(Button(btn_lbl, id=f"nav-pl-{pl['id']}", classes=btn_classes))
                await pl_container.mount(*btns)
        except Exception:
            pass

    def _set_active_nav(self, active_index: int):
        liked_count = len(self.db.get_liked_songs())
        queue_count = len(self.player.queue)
        radio_count = len(self.player.radio_queue)
        nav_names = {
            1: "SEARCH",
            2: f"QUEUE ({queue_count})",
            3: f"LIKED ({liked_count})",
            4: "HISTORY",
            5: f"RADIO ({radio_count})"
        }
        for i in range(1, 6):
            try:
                btn = self.query_one(f"#nav-btn-{i}", Button)
                name = nav_names[i]
                if i == active_index:
                    btn.label = f"> {i}. {name}"
                    btn.add_class("nav-active")
                else:
                    btn.label = f"  {i}. {name}"
                    btn.remove_class("nav-active")
            except Exception:
                pass
        try:
            for btn in self.query("#sidebar-playlists Button"):
                btn.remove_class("nav-active")
                lbl_text = str(btn.label)
                if lbl_text.startswith("> "):
                    btn.label = lbl_text.replace("> ", "  ")
        except Exception:
            pass

    def _set_active_nav_playlist(self, active_pl_id: int):
        for i in range(1, 6):
            try:
                btn = self.query_one(f"#nav-btn-{i}", Button)
                btn.remove_class("nav-active")
                lbl_text = str(btn.label)
                if lbl_text.startswith("> "):
                    btn.label = lbl_text.replace("> ", "  ")
            except Exception:
                pass
        try:
            for btn in self.query("#sidebar-playlists Button"):
                btn_id = btn.id or ""
                lbl_text = str(btn.label)
                if btn_id == f"nav-pl-{active_pl_id}":
                    btn.add_class("nav-active")
                    if lbl_text.startswith("  "):
                        btn.label = lbl_text.replace("  ", "> ")
                else:
                    btn.remove_class("nav-active")
                    if lbl_text.startswith("> "):
                        btn.label = lbl_text.replace("> ", "  ")
        except Exception:
            pass

    # ---------------- VIEW SWITCHING & DYNAMIC HEADER ACTIONS ----------------

    def _update_view_header(self):
        try:
            title_lbl = self.query_one("#view-title", Label)
            actions_box = self.query_one("#view-actions", Horizontal)
            self.run_worker(self._render_view_actions(title_lbl, actions_box))
        except Exception:
            pass

    async def _render_view_actions(self, title_lbl: Label, actions_box: Horizontal):
        try:
            await actions_box.remove_children()
            if self.current_view == "SEARCH":
                count = len(self.tracks_in_table)
                suffix = f" ({count} hasil)" if count else ""
                title_lbl.update(f"[CARI LAGU YOUTUBE]{suffix}")
            elif self.current_view == "QUEUE":
                q_len = len(self.player.queue)
                title_lbl.update(f"[DAFTAR ANTREAN - QUEUE] ({q_len} lagu)")
                if q_len > 0:
                    await actions_box.mount(Button(Content("[ Kosongkan ]"), id="btn-act-clear-queue", classes="view-action-btn modal-btn-danger"))
            elif self.current_view == "RADIO":
                r_len = len(self.player.radio_queue)
                cur = self.player.current_track
                seed_title = f"'{cur.get('title', '')[:25]}'" if cur else "Lagu Aktif"
                auto_str = "ON" if self.player.autoplay else "OFF"
                title_lbl.update(f"[RADIO MIX] Berdasarkan: {seed_title} ({r_len} lagu) [Radio: {auto_str}]")
                if r_len > 0:
                    await actions_box.mount(
                        Button(Content("[ Refresh Radio ]"), id="btn-act-refresh-radio", classes="view-action-btn"),
                        Button(Content("[ Putar Semua ]"), id="btn-act-play-all-radio", classes="view-action-btn")
                    )
            elif self.current_view == "LIKED":
                liked = self.db.get_liked_songs()
                title_lbl.update(f"[LAGU FAVORIT / LIKED SONGS] ({len(liked)} lagu)")
                if len(liked) > 0:
                    await actions_box.mount(
                        Button(Content("[ Download Semua ]"), id="btn-act-download-liked", classes="view-action-btn")
                    )
            elif self.current_view == "HISTORY":
                hist = self.db.get_history(50)
                title_lbl.update(f"[RIWAYAT PEMUTARAN - HISTORY] ({len(hist)} lagu)")
                if len(hist) > 0:
                    await actions_box.mount(Button(Content("[ Bersihkan ]"), id="btn-act-clear-history", classes="view-action-btn modal-btn-danger"))
            elif self.current_view.startswith("PLAYLIST:"):
                pl_id = int(self.current_view.split(":")[1])
                pl = self.db.get_playlist(pl_id)
                pl_name = pl["name"] if pl else "Playlist"
                tracks = self.db.get_playlist_tracks(pl_id)
                title_lbl.update(f"[PLAYLIST: {pl_name.upper()}] ({len(tracks)} lagu)")
                buttons = []
                if len(tracks) > 0:
                    buttons.append(Button(Content("[ Download Semua ]"), id="btn-act-download-pl", classes="view-action-btn"))
                buttons.append(Button(Content("[ Ubah Nama ]"), id="btn-act-rename-pl", classes="view-action-btn"))
                buttons.append(Button(Content("[ Hapus PL ]"), id="btn-act-delete-pl", classes="view-action-btn modal-btn-danger"))
                await actions_box.mount(*buttons)
        except Exception:
            pass

    def action_nav_search(self):
        self.current_view = "SEARCH"
        self._set_active_nav(1)
        self.query_one("#search-input", Input).display = True
        self.query_one("#search-status", Label).display = True
        self._populate_table(self.tracks_in_table)
        self._update_view_header()
        self.query_one("#search-input", Input).focus()

    def action_nav_queue(self):
        self.current_view = "QUEUE"
        self._set_active_nav(2)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        self._populate_table(self.player.queue)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_liked(self):
        self.current_view = "LIKED"
        self._set_active_nav(3)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        liked = self.db.get_liked_songs()
        self._populate_table(liked)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_history(self):
        self.current_view = "HISTORY"
        self._set_active_nav(4)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        history = self.db.get_history(50)
        self._populate_table(history)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_radio(self):
        self.current_view = "RADIO"
        self._set_active_nav(5)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        self._populate_table(self.player.radio_queue)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_playlist(self, pl_id: int):
        pl = self.db.get_playlist(pl_id)
        if not pl:
            return
        self.current_view = f"PLAYLIST:{pl_id}"
        self._set_active_nav_playlist(pl_id)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        tracks = self.db.get_playlist_tracks(pl_id)
        self._populate_table(tracks)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    # ---------------- SPOTIFY-STYLE TRACK LIST RENDERING ----------------

    def _populate_table(self, tracks: List[Dict]):
        if self.current_view == "SEARCH":
            self.tracks_in_table = tracks
        self.run_worker(self._render_tracks(tracks), exclusive=True)

    async def _render_tracks(self, tracks: List[Dict]):
        scroll = self.query_one("#tracks-scroll", VerticalScroll)
        await scroll.remove_children()
        if not tracks:
            msg = "Belum ada lagu untuk ditampilkan."
            if self.current_view == "SEARCH":
                msg = "Ketik judul lagu / artis di atas dan tekan Enter untuk mencari."
            elif self.current_view == "QUEUE":
                msg = "Antrean kosong. Tekan 'e' [+Next] atau 'a' [+Q] pada lagu untuk menambah antrean."
            elif self.current_view == "RADIO":
                msg = "Belum ada rekomendasi radio. Putar sebuah lagu untuk mengaktifkan radio mix otomatis."
            elif self.current_view == "LIKED":
                msg = "Belum ada lagu favorit. Tekan 'f' atau klik [Fav] pada lagu untuk menyimpannya."
            elif self.current_view.startswith("PLAYLIST:"):
                msg = "Playlist masih kosong. Tekan 'm' atau klik [+PL] pada lagu untuk memasukkannya."
            await scroll.mount(Label(f"  {msg}", classes="empty-state", markup=False))
            self.selected_idx = 0
            return

        cur_id = self.player.current_track.get("id") if self.player.current_track else None
        self.selected_idx = min(self.selected_idx, max(0, len(tracks) - 1))

        rows = []
        for idx, track in enumerate(tracks):
            t_id = track.get("id", "")
            is_playing = (cur_id is not None and cur_id == t_id)
            is_liked = self.db.is_liked(t_id)
            is_selected = (idx == self.selected_idx)
            is_radio = bool(track.get("is_radio", False))
            rows.append(TrackRow(idx, track, is_selected=is_selected, is_playing=is_playing, is_liked=is_liked, is_radio=is_radio))

        await scroll.mount(*rows)

    # ---------------- SEARCH & IMPORT HANDLING ----------------

    async def on_input_submitted(self, event: Input.Submitted):
        query = event.value.strip()
        if not query:
            return

        if is_playlist_url(query):
            self.query_one("#search-input", Input).value = ""
            self.action_import_playlist(initial_url=query)
            return

        self._current_search_query = query
        self._search_spinner_idx = 0
        if self._search_spinner_timer:
            self._search_spinner_timer.stop()
        self._search_spinner_timer = self.set_interval(0.12, self._tick_search_spinner)
        self.perform_search(query)

    @work(exclusive=True, group="import_playlist", thread=False)
    async def import_youtube_playlist(self, url: str, custom_name: Optional[str] = None):
        status_lbl = self.query_one("#search-status", Label)
        status_lbl.update("[IMPORT] Mengambil daftar lagu dari YouTube Playlist...")
        self.notify("[IMPORT] Mengambil metadata playlist dari YouTube...", timeout=2.5)

        pl_title, tracks = await fetch_youtube_playlist(url, limit=150)

        if not tracks:
            status_lbl.update("[ERROR] Gagal mengambil playlist atau playlist kosong / privat.")
            self.notify("[ERROR] Gagal mengambil playlist YouTube. Pastikan link publik & valid.", timeout=3.0)
            return

        final_title = custom_name.strip() if custom_name and custom_name.strip() else pl_title
        pl_id = self.db.create_playlist(final_title)
        if not pl_id:
            self.notify("[ERROR] Gagal membuat playlist di database.", timeout=2.5)
            return

        added_count = 0
        for tr in tracks:
            if self.db.add_to_playlist(pl_id, tr):
                added_count += 1

        self._update_sidebar_counts()
        self._refresh_playlists_sidebar()
        self.action_nav_playlist(pl_id)
        self.notify(f"[PLAYLIST] Berhasil import '{final_title}' ({added_count} lagu)!", timeout=3.5)

    def _tick_search_spinner(self):
        frame = self._spinner_frames[self._search_spinner_idx % len(self._spinner_frames)]
        self._search_spinner_idx += 1
        status_lbl = self.query_one("#search-status", Label)
        status_lbl.update(f"Mencari: \"{self._current_search_query}\" {frame}")

    @work(exclusive=True, group="search", thread=False)
    async def perform_search(self, query: str):
        # 1. Fetch initial batch of 15 fast
        results = await search_youtube(query, limit=15)
        if self._search_spinner_timer:
            self._search_spinner_timer.stop()
            self._search_spinner_timer = None

        status_lbl = self.query_one("#search-status", Label)

        if not results:
            status_lbl.update(f"Tidak ada hasil untuk: \"{query}\". Coba kata kunci lain.")
            return

        self.tracks_in_table = list(results)
        self.selected_idx = 0
        status_lbl.update(f"Ditemukan {len(results)} lagu (memuat lebih banyak...). Gunakan Panah + Enter.")
        self._populate_table(results)
        self.query_one("#tracks-scroll", VerticalScroll).focus()

        # 2. Asynchronously fetch extended batch (up to 40) in background without flicker
        asyncio.create_task(self._fetch_extended_search(query, existing_ids={r.get("id") for r in results if r.get("id")}))

    async def _fetch_extended_search(self, query: str, existing_ids: set):
        try:
            more_results = await search_youtube(query, limit=40)
            if self.current_view != "SEARCH" or self._current_search_query != query:
                return
            new_tracks = [t for t in more_results if t.get("id") and t.get("id") not in existing_ids]
            if not new_tracks:
                try:
                    self.query_one("#search-status", Label).update(
                        f"Ditemukan {len(self.tracks_in_table)} lagu. Gunakan Panah Bawah/Atas + Enter."
                    )
                except Exception:
                    pass
                return

            start_idx = len(self.tracks_in_table)
            self.tracks_in_table.extend(new_tracks)

            cur_id = self.player.current_track.get("id") if self.player.current_track else None
            new_rows = []
            for i, track in enumerate(new_tracks):
                idx = start_idx + i
                t_id = track.get("id", "")
                is_playing = bool(cur_id and cur_id == t_id)
                is_liked = self.db.is_liked(t_id)
                new_rows.append(TrackRow(idx, track, is_selected=False, is_playing=is_playing, is_liked=is_liked))

            scroll = self.query_one("#tracks-scroll", VerticalScroll)
            await scroll.mount(*new_rows)

            try:
                self.query_one("#search-status", Label).update(
                    f"Ditemukan {len(self.tracks_in_table)} lagu. Gunakan Panah Bawah/Atas + Enter."
                )
                self._update_view_header()
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- KEYBOARD CURSOR NAVIGATION ----------------

    def action_cursor_down(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            self.query_one("#tracks-scroll", VerticalScroll).focus()
            return
        active_list = self._get_active_list()
        if not active_list:
            return
        if self.selected_idx < len(active_list) - 1:
            self._select_row(self.selected_idx + 1)

    def action_cursor_up(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        active_list = self._get_active_list()
        if not active_list:
            return
        if self.selected_idx > 0:
            self._select_row(self.selected_idx - 1)

    def action_move_track_up(self):
        """Move selected track up in Queue or Playlist."""
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        if self.current_view == "QUEUE":
            if 0 < self.selected_idx < len(self.player.queue):
                new_idx = self.selected_idx - 1
                self.player.move_queue(self.selected_idx, new_idx)
                self.db.save_queue(self.player.queue)
                self.selected_idx = new_idx
                self._populate_table(self._get_active_list())
                self.notify("[QUEUE] Posisi lagu dipindahkan ke atas.", timeout=1.5)
        elif self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            tracks = self.db.get_playlist_tracks(pl_id)
            if 0 < self.selected_idx < len(tracks):
                new_idx = self.selected_idx - 1
                if self.db.move_playlist_track(pl_id, self.selected_idx, new_idx):
                    self.selected_idx = new_idx
                    self._populate_table(self.db.get_playlist_tracks(pl_id))
                    self.notify("[PLAYLIST] Posisi lagu dipindahkan ke atas.", timeout=1.5)

    def action_move_track_down(self):
        """Move selected track down in Queue or Playlist."""
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        if self.current_view == "QUEUE":
            if 0 <= self.selected_idx < len(self.player.queue) - 1:
                new_idx = self.selected_idx + 1
                self.player.move_queue(self.selected_idx, new_idx)
                self.db.save_queue(self.player.queue)
                self.selected_idx = new_idx
                self._populate_table(self._get_active_list())
                self.notify("[QUEUE] Posisi lagu dipindahkan ke bawah.", timeout=1.5)
        elif self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            tracks = self.db.get_playlist_tracks(pl_id)
            if 0 <= self.selected_idx < len(tracks) - 1:
                new_idx = self.selected_idx + 1
                if self.db.move_playlist_track(pl_id, self.selected_idx, new_idx):
                    self.selected_idx = new_idx
                    self._populate_table(self.db.get_playlist_tracks(pl_id))
                    self.notify("[PLAYLIST] Posisi lagu dipindahkan ke bawah.", timeout=1.5)

    def _select_row(self, new_idx: int):
        old_idx = self.selected_idx
        self.selected_idx = new_idx
        try:
            self.query_one(f"#row-{old_idx}", TrackRow).remove_class("row-selected")
        except Exception:
            pass
        try:
            new_row = self.query_one(f"#row-{new_idx}", TrackRow)
            new_row.add_class("row-selected")
            new_row.scroll_visible(animate=False)
        except Exception:
            pass

    def action_play_selected(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        self._play_track_at_index(self.selected_idx)

    # ---------------- INTERACTIVE CLICK & ACTION HANDLERS ----------------

    @on(Click, ".track-row")
    def on_row_click(self, event: Click):
        if isinstance(event.widget, Button):
            return
        row = event.widget if isinstance(event.widget, TrackRow) else event.widget.ancestor(TrackRow)
        if row:
            self._select_row(row.idx)
            self._play_track_at_index(row.idx)

    def _play_track_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            subsequent = active_list[idx + 1:]
            if self.current_view.startswith("PLAYLIST:") or self.current_view == "LIKED":
                # Context queue follows playlist sequence, keeping full context for Repeat ALL/Shuffle
                self.player.full_context_list = list(active_list)
                if self.player.shuffle:
                    shuffled_rem = [t for i, t in enumerate(active_list) if i != idx]
                    random.shuffle(shuffled_rem)
                    self.player.context_queue = shuffled_rem
                else:
                    self.player.context_queue = list(subsequent)
                self._play_track(track)
            elif self.current_view == "SEARCH":
                # Spotify-style: search does NOT hijack or overwrite user queue!
                self.player.context_queue = []
                self._play_track(track)
            elif self.current_view == "QUEUE":
                if 0 <= idx < len(self.player.queue):
                    self.player.queue.pop(idx)
                    self.db.save_queue(self.player.queue)
                self._play_track(track)
                self._update_sidebar_counts()
                self._populate_table(self.player.queue)
                self._update_view_header()
            elif self.current_view == "RADIO":
                if 0 <= idx < len(self.player.radio_queue):
                    self.player.radio_queue = list(self.player.radio_queue[idx + 1:])
                self._play_track(track)
                self._update_sidebar_counts()
                self._update_row_playing_states(track.get("id"))
                self._update_view_header()

    def _play_next_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            self.player.play_next_enqueue(track)
            self.db.save_queue(self.player.queue)
            self._update_sidebar_counts()
            title = track.get("title", "")[:35]
            self.notify(f"[NEXT] Disisipkan berikutnya: {title}", timeout=2.0)
            if self.current_view == "QUEUE":
                self._populate_table(self._get_active_list())
                self._update_view_header()

    def action_play_next_item(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        self._play_next_at_index(self.selected_idx)

    def _add_to_queue_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            self.player.add_to_queue(track)
            self.db.save_queue(self.player.queue)
            self._update_sidebar_counts()
            title = track.get("title", "")[:35]
            self.notify(f"[QUEUE] Ditambahkan: {title}", timeout=2.0)
            if self.current_view == "QUEUE":
                self._populate_table(self._get_active_list())
                self._update_view_header()

    def _open_playlist_menu_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            self._show_playlist_modal_for_track(track)

    def _toggle_like_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            vid_id = track.get("id", "")
            btn = None
            try:
                btn = self.query_one(f"#btn-row-fav-{idx}", Button)
            except Exception:
                pass
            if self.db.is_liked(vid_id):
                self.db.remove_liked(vid_id)
                self.notify("[LIKED] Dihapus dari Favorit", timeout=2.0)
                if btn:
                    btn.label = Content("[ Fav ]")
                    btn.remove_class("is-liked")
            else:
                self.db.add_liked(
                    vid_id,
                    track.get("title", ""),
                    track.get("artist", ""),
                    track.get("duration", ""),
                    track.get("duration_sec", 0),
                    track.get("url", "")
                )
                self.notify("[LIKED] Disimpan ke Favorit!", timeout=2.0)
                if btn:
                    btn.label = Content("[ Liked ]")
                    btn.add_class("is-liked")
                asyncio.create_task(self._auto_cache_track(track))
            self._update_sidebar_counts()
            if self.current_view == "LIKED":
                self._populate_table(self.db.get_liked_songs())
                self._update_view_header()

    def _get_active_list(self) -> List[Dict]:
        if self.current_view == "SEARCH":
            return self.tracks_in_table
        elif self.current_view == "QUEUE":
            return self.player.queue
        elif self.current_view == "RADIO":
            return self.player.radio_queue
        elif self.current_view == "LIKED":
            return self.db.get_liked_songs()
        elif self.current_view == "HISTORY":
            return self.db.get_history(50)
        elif self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            return self.db.get_playlist_tracks(pl_id)
        return []

    def _play_track(self, track: Dict):
        self.is_loading_track = True
        self.loading_track_info = track
        self._load_symbol_idx = 0
        self.player.play(track)
        self.db.add_history(
            track.get("id", ""),
            track.get("title", ""),
            track.get("artist", ""),
            track.get("duration", ""),
            track.get("duration_sec", 0),
            track.get("url", "")
        )
        self._update_player_display_loading(track)
        if self.player.autoplay:
            asyncio.create_task(self._refresh_radio_recommendations(track))
        if self.current_view == "QUEUE":
            self._refresh_current_view()
        else:
            self._update_row_playing_states(track.get("id"))
            self._update_sidebar_counts()

    async def _refresh_radio_recommendations(self, seed_track: Dict):
        v_id = seed_track.get("id", "")
        if not v_id:
            return
        artist = seed_track.get("artist", "")
        title = seed_track.get("title", "")
        try:
            recs = await fetch_radio_mix(v_id, artist=artist, title=title, limit=12)
            if recs:
                existing_ids = {self.player.current_track.get("id")} if self.player.current_track else set()
                existing_ids.update(t.get("id") for t in self.player.queue if t.get("id"))
                existing_ids.update(t.get("id") for t in self.player.context_queue if t.get("id"))
                existing_ids.update(self.player.session_played_ids)

                filtered = []
                for r in recs:
                    if r.get("id") and r.get("id") not in existing_ids:
                        r["is_radio"] = True
                        filtered.append(r)
                if filtered:
                    self.player.radio_queue = filtered
                    self._update_sidebar_counts()
                    if self.current_view == "RADIO":
                        scroll = self.query_one("#tracks-scroll", VerticalScroll)
                        # Only re-populate table if it was empty or showing empty message
                        has_tracks = bool(scroll.children and not any(isinstance(c, Label) and c.has_class("empty-state") for c in scroll.children))
                        if not has_tracks:
                            self._populate_table(self.player.radio_queue)
                        else:
                            self._update_row_playing_states(seed_track.get("id"))
                        self._update_view_header()
        except Exception:
            pass

    def _update_row_playing_states(self, playing_track_id: Optional[str]):
        """Update playing indicator on existing rows in-place without re-rendering the DOM."""
        try:
            for row in self.query(TrackRow):
                is_this = bool(playing_track_id and row.track.get("id") == playing_track_id)
                row.is_playing = is_this
                if is_this:
                    row.add_class("row-playing")
                else:
                    row.remove_class("row-playing")
                try:
                    btn = row.query_one(f"#btn-row-play-{row.idx}", Button)
                    btn.label = Content("[ || ]") if is_this else Content("[ > ]")
                except Exception:
                    pass
        except Exception:
            pass

    def _update_row_cache_states(self, track_id: Optional[str] = None):
        """Update offline [v] indicator on existing rows in-place without re-rendering DOM."""
        try:
            for row in self.query(TrackRow):
                row_id = row.track.get("id")
                if track_id is None or row_id == track_id:
                    cached = is_track_cached(row_id)
                    try:
                        lbl = row.query_one(f"#lbl-row-cache-{row.idx}", Label)
                        lbl.update("[v]" if cached else "   ")
                        if cached:
                            lbl.add_class("is-cached")
                        else:
                            lbl.remove_class("is-cached")
                    except Exception:
                        pass
        except Exception:
            pass

    async def _auto_cache_track(self, track: Dict):
        """Silently download audio in background when liked or added to playlist."""
        vid_id = track.get("id")
        if not vid_id or is_track_cached(vid_id):
            return
        success = await download_track_audio(track)
        if success:
            self._update_row_cache_states(vid_id)

    @work(exclusive=True, group="batch_download", thread=False)
    async def _download_tracks_batch(self, tracks: List[Dict], container_name: str):
        """Batch sequential background download with live notification and indicator update."""
        to_download = [t for t in tracks if t.get("id") and not is_track_cached(t.get("id"))]
        total = len(to_download)
        if total == 0:
            self.notify(f"[{container_name.upper()}] Semua lagu sudah ter-download offline!", timeout=3.0)
            return

        self.notify(f"[{container_name.upper()}] Memulai download {total} lagu di background...", timeout=3.0)
        done = 0
        for track in to_download:
            vid_id = track.get("id")
            ok = await download_track_audio(track)
            if ok:
                done += 1
                self._update_row_cache_states(vid_id)
        self.notify(f"[{container_name.upper()}] Selesai! {done}/{total} lagu tersimpan di cache offline.", timeout=4.0)

    def _refresh_current_view(self):
        active = self._get_active_list()
        self._populate_table(active)
        self._update_sidebar_counts()

    # ---------------- KEYBOARD ACTION SHORTCUTS ----------------

    def action_add_queue(self):
        """Add highlighted track to queue with key 'a'."""
        self._add_to_queue_at_index(self.selected_idx)

    def action_open_playlist_menu(self):
        """Add highlighted track to a playlist with key 'm'."""
        self._open_playlist_menu_at_index(self.selected_idx)

    def _show_playlist_modal_for_track(self, track: Dict):
        playlists = self.db.get_playlists()

        def handle_select_pl(result: Optional[int]):
            if result is None:
                return
            if result == -1:
                self.action_create_new_playlist(initial_track=track)
            else:
                self.db.add_to_playlist(result, track)
                asyncio.create_task(self._auto_cache_track(track))
                pl = self.db.get_playlist(result)
                pl_name = pl["name"] if pl else "Playlist"
                self.notify(f"[PLAYLIST] Disimpan ke '{pl_name}'!", timeout=2.5)
                self._update_sidebar_counts()
                self._refresh_playlists_sidebar()
                if self.current_view == f"PLAYLIST:{result}":
                    self._populate_table(self.db.get_playlist_tracks(result))

        self.push_screen(PlaylistSelectModal(track, playlists), handle_select_pl)

    def action_create_new_playlist(self, initial_track: Optional[Dict] = None):
        """Prompt modal to create a new playlist."""
        def handle_new_pl(name: Optional[str]):
            if not name:
                return
            pl_id = self.db.create_playlist(name)
            if not pl_id:
                self.notify("[ERROR] Gagal membuat playlist.", timeout=2.0)
                return
            if initial_track:
                self.db.add_to_playlist(pl_id, initial_track)
                asyncio.create_task(self._auto_cache_track(initial_track))
                self.notify(f"[PLAYLIST] '{name}' dibuat & lagu ditambahkan!", timeout=2.5)
            else:
                self.notify(f"[PLAYLIST] Playlist '{name}' berhasil dibuat!", timeout=2.5)
            self._update_sidebar_counts()
            self._refresh_playlists_sidebar()
            self.action_nav_playlist(pl_id)

        self.push_screen(NewPlaylistModal(), handle_new_pl)

    def action_import_playlist(self, initial_url: str = ""):
        """Prompt modal to import a YouTube playlist with custom name."""
        def handle_import_data(result: Optional[Dict[str, str]]):
            if not result or not result.get("url"):
                return
            url = result["url"]
            name = result.get("name")
            self.import_youtube_playlist(url, custom_name=name)

        self.push_screen(ImportPlaylistModal(initial_url=initial_url), handle_import_data)

    def action_delete_item(self):
        """Delete highlighted track from current playlist or queue with key 'd'."""
        if self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            active_list = self._get_active_list()
            if 0 <= self.selected_idx < len(active_list):
                track = active_list[self.selected_idx]
                if self.db.remove_from_playlist(pl_id, self.selected_idx):
                    title = track.get("title", "")[:30]
                    self.notify(f"[PLAYLIST] Dihapus: {title}", timeout=2.0)
                    self._populate_table(self.db.get_playlist_tracks(pl_id))
                    self._update_sidebar_counts()
                    self._refresh_playlists_sidebar()
                    self._update_view_header()
            elif len(active_list) == 0:
                self._confirm_delete_playlist(pl_id)
        elif self.current_view == "LIKED":
            self.action_toggle_like()
        elif self.current_view == "QUEUE":
            if 0 <= self.selected_idx < len(self.player.queue):
                removed = self.player.remove_from_queue(self.selected_idx)
                if removed:
                    self.db.save_queue(self.player.queue)
                    title = removed.get("title", "")[:30]
                    self.notify(f"[QUEUE] Dihapus: {title}", timeout=2.0)
                    self._populate_table(self.player.queue)
                    self._update_sidebar_counts()
                    self._update_view_header()
        elif self.current_view == "RADIO":
            if 0 <= self.selected_idx < len(self.player.radio_queue):
                removed = self.player.radio_queue.pop(self.selected_idx)
                if removed:
                    title = removed.get("title", "")[:30]
                    self.notify(f"[RADIO] Dihapus dari rekomendasi: {title}", timeout=2.0)
                    self._populate_table(self.player.radio_queue)
                    self._update_sidebar_counts()
                    self._update_view_header()

    def _confirm_delete_playlist(self, pl_id: int):
        pl = self.db.get_playlist(pl_id)
        pl_name = pl["name"] if pl else "Playlist"

        def on_confirm(yes: bool):
            if yes:
                self.db.delete_playlist(pl_id)
                self.notify(f"[PLAYLIST] '{pl_name}' berhasil dihapus.", timeout=2.5)
                self.action_nav_search()
                self._update_sidebar_counts()
                self._refresh_playlists_sidebar()

        self.push_screen(ConfirmModal("HAPUS PLAYLIST", f"Yakin ingin menghapus playlist '{pl_name}' secara permanen?"), on_confirm)

    def action_rename_current_playlist(self):
        """Prompt modal to rename the currently viewed playlist."""
        if not self.current_view.startswith("PLAYLIST:"):
            self.notify("[INFO] Buka sebuah playlist terlebih dahulu untuk mengubah namanya.", timeout=2.0)
            return

        pl_id = int(self.current_view.split(":")[1])
        pl = self.db.get_playlist(pl_id)
        if not pl:
            return

        def handle_rename(new_name: Optional[str]):
            if not new_name or new_name == pl["name"]:
                return
            if self.db.rename_playlist(pl_id, new_name):
                self.notify(f"[PLAYLIST] Berhasil diubah menjadi '{new_name}'!", timeout=2.5)
                self._update_sidebar_counts()
                self._refresh_playlists_sidebar()
                self._update_view_header()
            else:
                self.notify("[ERROR] Gagal mengubah nama playlist (mungkin nama sudah ada).", timeout=2.5)

        self.push_screen(RenamePlaylistModal(pl["name"]), handle_rename)

    def action_clear_current_view(self):
        """Clear active queue or playback history with confirmation."""
        if self.current_view == "QUEUE":
            if not self.player.queue:
                self.notify("[QUEUE] Antrean sudah kosong.", timeout=2.0)
                return

            def on_confirm_clear_queue(yes: bool):
                if yes:
                    self.player.clear_queue()
                    self.db.clear_queue()
                    self._populate_table([])
                    self._update_sidebar_counts()
                    self._update_view_header()
                    self.notify("[QUEUE] Seluruh antrean berhasil dikosongkan.", timeout=2.0)

            self.push_screen(ConfirmModal("KOSONGKAN ANTREAN", "Yakin ingin menghapus semua lagu dari antrean?"), on_confirm_clear_queue)

        elif self.current_view == "HISTORY":
            hist = self.db.get_history(50)
            if not hist:
                self.notify("[HISTORY] Riwayat sudah kosong.", timeout=2.0)
                return

            def on_confirm_clear_history(yes: bool):
                if yes:
                    self.db.clear_history()
                    self._populate_table([])
                    self._update_view_header()
                    self.notify("[HISTORY] Seluruh riwayat pemutaran telah dibersihkan.", timeout=2.0)

            self.push_screen(ConfirmModal("BERSIHKAN RIWAYAT", "Yakin ingin menghapus seluruh riwayat pemutaran?"), on_confirm_clear_history)

    def action_toggle_like(self):
        """Bookmark/like highlighted track with key 'f'."""
        self._toggle_like_at_index(self.selected_idx)

    def action_toggle_pause(self):
        self.player.toggle_pause()
        if self.player.current_track:
            cur_id = self.player.current_track.get("id")
            for row in self.query(TrackRow):
                if row.track.get("id") == cur_id:
                    try:
                        btn = row.query_one(f"#btn-row-play-{row.idx}", Button)
                        btn.label = Content("[ > ]") if self.player.is_paused else Content("[ || ]")
                    except Exception:
                        pass

    def action_prev_track(self):
        prev_track = self.player.play_previous()
        if prev_track:
            self._play_track(prev_track)
        else:
            self.notify("[PLAYER] Tidak ada riwayat lagu sebelumnya.", timeout=2.0)

    def action_next_track(self, is_eof: bool = False):
        next_track = self.player.play_next(is_eof=is_eof)
        self.db.save_queue(self.player.queue)
        self._update_sidebar_counts()
        if next_track:
            self._play_track(next_track)
        else:
            self.notify("[QUEUE] Antrean lagu telah selesai.", timeout=2.0)
        if self.current_view in ("QUEUE", "RADIO"):
            self._populate_table(self._get_active_list())
            self._update_view_header()

    def action_toggle_like_now_playing(self):
        """Toggle like/favorite on the currently playing track (hotkey 'F' or click [Fav])."""
        track = self.player.current_track
        if not track or not track.get("id"):
            self.notify("[FAV] Tidak ada lagu yang sedang diputar.", timeout=1.5)
            return

        vid_id = track.get("id", "")
        if self.db.is_liked(vid_id):
            self.db.remove_liked(vid_id)
            title = track.get("title", "")[:30]
            self.notify(f"[LIKED] Dihapus dari Favorit: {title}", timeout=2.0)
        else:
            self.db.add_liked(
                vid_id,
                track.get("title", ""),
                track.get("artist", ""),
                track.get("duration", ""),
                track.get("duration_sec", 0),
                track.get("url", "")
            )
            title = track.get("title", "")[:30]
            self.notify(f"[LIKED] Disimpan ke Favorit: {title}", timeout=2.0)
            asyncio.create_task(self._auto_cache_track(track))

        self._update_sidebar_counts()
        for row in self.query(TrackRow):
            if row.track.get("id") == vid_id:
                is_liked = self.db.is_liked(vid_id)
                row.is_liked = is_liked
                try:
                    b = row.query_one(f"#btn-row-fav-{row.idx}", Button)
                    b.label = Content("[ Liked ]") if is_liked else Content("[ Fav ]")
                    if is_liked:
                        b.add_class("is-liked")
                    else:
                        b.remove_class("is-liked")
                except Exception:
                    pass
        if self.current_view == "LIKED":
            self._populate_table(self.db.get_liked_songs())
            self._update_view_header()

    def action_toggle_shuffle(self):
        """Toggle shuffle mode (hotkey 's')."""
        is_shuf = self.player.toggle_shuffle()
        self._save_current_player_state()
        state_str = "ON (Acak)" if is_shuf else "OFF (Normal)"
        self.notify(f"[SHUFFLE] Mode Acak: {state_str}", timeout=1.5)

    def action_toggle_repeat(self):
        """Cycle repeat mode: OFF -> ALL -> ONE -> OFF (hotkey 't')."""
        mode = self.player.toggle_repeat()
        self._save_current_player_state()
        desc = {
            "OFF": "OFF (Tidak Ulang)",
            "ALL": "ALL (Ulang Playlist)",
            "ONE": "ONE (Ulang 1 Lagu)"
        }.get(mode, mode)
        self.notify(f"[REPEAT] Mode Putar Ulang: {desc}", timeout=1.5)

    @on(Button.Pressed)
    def on_button_click(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        # View Header Actions (Playlist, Queue, History)
        if btn_id == "btn-act-clear-queue":
            self.action_clear_current_view()
        elif btn_id == "btn-act-clear-history":
            self.action_clear_current_view()
        elif btn_id == "btn-act-download-liked":
            liked = self.db.get_liked_songs()
            self._download_tracks_batch(liked, "Favorit")
        elif btn_id == "btn-act-download-pl":
            if self.current_view.startswith("PLAYLIST:"):
                pl_id = int(self.current_view.split(":")[1])
                pl = self.db.get_playlist(pl_id)
                pl_name = pl["name"] if pl else "Playlist"
                tracks = self.db.get_playlist_tracks(pl_id)
                self._download_tracks_batch(tracks, pl_name)
        elif btn_id == "btn-act-rename-pl":
            self.action_rename_current_playlist()
        elif btn_id == "btn-act-delete-pl":
            if self.current_view.startswith("PLAYLIST:"):
                pl_id = int(self.current_view.split(":")[1])
                self._confirm_delete_playlist(pl_id)
        # Row action buttons
        elif btn_id.startswith("btn-row-play-"):
            idx = int(btn_id.replace("btn-row-play-", ""))
            self._select_row(idx)
            self._play_track_at_index(idx)
        elif btn_id.startswith("btn-row-next-"):
            idx = int(btn_id.replace("btn-row-next-", ""))
            self._play_next_at_index(idx)
        elif btn_id.startswith("btn-row-q-"):
            idx = int(btn_id.replace("btn-row-q-", ""))
            self._add_to_queue_at_index(idx)
        elif btn_id.startswith("btn-row-pl-"):
            idx = int(btn_id.replace("btn-row-pl-", ""))
            self._open_playlist_menu_at_index(idx)
        elif btn_id.startswith("btn-row-fav-"):
            idx = int(btn_id.replace("btn-row-fav-", ""))
            self._toggle_like_at_index(idx)
        # Player bottom controls
        elif btn_id == "btn-play":
            self.action_toggle_pause()
        elif btn_id == "btn-prev":
            self.action_prev_track()
        elif btn_id == "btn-next":
            self.action_next_track()
        elif btn_id == "btn-seek-back":
            self.action_seek_backward()
        elif btn_id == "btn-seek-fwd":
            self.action_seek_forward()
        elif btn_id == "btn-vol-down":
            self.action_vol_down()
        elif btn_id == "btn-vol-up":
            self.action_vol_up()
        elif btn_id == "btn-player-fav":
            self.action_toggle_like_now_playing()
        elif btn_id == "btn-toggle-shuffle":
            self.action_toggle_shuffle()
        elif btn_id == "btn-toggle-repeat":
            self.action_toggle_repeat()
        elif btn_id == "btn-toggle-autoplay":
            self.action_toggle_autoplay()
        # Sidebar Navigation
        elif btn_id == "nav-btn-1":
            self.action_nav_search()
        elif btn_id == "nav-btn-2":
            self.action_nav_queue()
        elif btn_id == "nav-btn-3":
            self.action_nav_liked()
        elif btn_id == "nav-btn-4":
            self.action_nav_history()
        elif btn_id == "nav-btn-5":
            self.action_nav_radio()
        elif btn_id == "btn-act-refresh-radio":
            if self.player.current_track:
                self.notify("[RADIO] Memperbarui daftar rekomendasi...", timeout=1.5)
                async def _do_manual_refresh():
                    seed = self.player.current_track
                    recs = await fetch_radio_mix(seed.get("id", ""), artist=seed.get("artist", ""), title=seed.get("title", ""), limit=15)
                    if recs:
                        for r in recs:
                            r["is_radio"] = True
                        self.player.radio_queue = recs
                        self._update_sidebar_counts()
                        if self.current_view == "RADIO":
                            self._populate_table(self.player.radio_queue)
                            self._update_view_header()
                asyncio.create_task(_do_manual_refresh())
            else:
                self.notify("[RADIO] Putar lagu terlebih dahulu.", timeout=2.0)
        elif btn_id == "btn-act-play-all-radio":
            if self.player.radio_queue:
                first = self.player.radio_queue.pop(0)
                self._play_track(first)
                self._update_sidebar_counts()
                self._populate_table(self.player.radio_queue)
                self._update_view_header()
        elif btn_id == "btn-sidebar-new-pl":
            self.action_create_new_playlist()
        elif btn_id == "btn-sidebar-import-pl":
            self.action_import_playlist()
        elif btn_id.startswith("nav-pl-"):
            pl_id = int(btn_id.replace("nav-pl-", ""))
            self.action_nav_playlist(pl_id)

    def action_toggle_autoplay(self):
        is_on = self.player.toggle_autoplay()
        self._save_current_player_state()
        try:
            btn = self.query_one("#btn-toggle-autoplay", Button)
            btn.label = Content(f"[ Radio: {'ON' if is_on else 'OFF'} ]")
        except Exception:
            pass
        self.notify(f"[AUTOPLAY] Mode Radio: {'ON' if is_on else 'OFF'}", timeout=1.5)
        self._update_sidebar_counts()
        if self.current_view == "RADIO":
            self._update_view_header()
            self._populate_table(self.player.radio_queue)

    def action_vol_up(self):
        self.player.set_volume(+5.0)
        self._save_current_player_state()
        try:
            stat_lbl = self.query_one("#player-status", Label)
            state_name = "Paused " if self.player.is_paused else ("Playing" if self.player.is_playing else "Ready  ")
            stat_lbl.update(f"STATUS: {state_name}                    VOL: " + make_vol_bar(self.player.volume))
        except Exception:
            pass
        self.notify(f"[VOLUME] {int(self.player.volume)}%", timeout=1.0)

    def action_vol_down(self):
        self.player.set_volume(-5.0)
        self._save_current_player_state()
        try:
            stat_lbl = self.query_one("#player-status", Label)
            state_name = "Paused " if self.player.is_paused else ("Playing" if self.player.is_playing else "Ready  ")
            stat_lbl.update(f"STATUS: {state_name}                    VOL: " + make_vol_bar(self.player.volume))
        except Exception:
            pass
        self.notify(f"[VOLUME] {int(self.player.volume)}%", timeout=1.0)

    def _save_current_player_state(self):
        try:
            cur_id = self.player.current_track.get("id") if self.player.current_track else None
            self.db.save_player_state(
                current_track_id=cur_id,
                queue_index=0,
                time_pos=self.player._last_time_pos,
                volume=self.player.volume,
                autoplay=self.player.autoplay,
                repeat_mode=self.player.repeat_mode,
                shuffle=self.player.shuffle
            )
        except Exception:
            pass

    def action_seek_forward(self):
        self.player.seek(+5.0)

    def action_seek_backward(self):
        self.player.seek(-5.0)

    def action_focus_search(self):
        if self.current_view != "SEARCH":
            self.action_nav_search()
        inp = self.query_one("#search-input", Input)
        inp.focus()

    def action_escape_focus(self):
        """Escape unfocuses search input and returns to track list."""
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    # ---------------- ATOMIC ZERO-FLICKER TICK ----------------

    def _update_player_display_loading(self, track: Dict):
        title_lbl = self.query_one("#player-title", Label)
        prog_lbl = self.query_one("#player-progress", Label)
        stat_lbl = self.query_one("#player-status", Label)

        frame = self._load_frames[self._load_symbol_idx % len(self._load_frames)]
        title_str = f"[LOAD {frame}] {track.get('title', '')} - {track.get('artist', '')}"
        title_lbl.update(title_str)
        dur = track.get("duration", "--:--")
        prog_lbl.update(f"00:00 [==>-----------------------------] {dur}")
        stat_lbl.update(f"STATUS: Loading {frame}                  VOL: " + make_vol_bar(self.player.volume))

    def tick_playback(self):
        """Atomic update of ONLY the 3 player labels (no table or layout re-rendering)."""
        try:
            status = self.player.get_status()

            # Handle song completion -> auto-play next in queue or repeat
            if status.get("eof"):
                self.action_next_track(is_eof=True)
                return

            title_lbl = self.query_one("#player-title", Label)
            prog_lbl = self.query_one("#player-progress", Label)
            stat_lbl = self.query_one("#player-status", Label)

            # Sync bottom player buttons (Fav, Shuffle, Repeat)
            try:
                fav_btn = self.query_one("#btn-player-fav", Button)
                if self.player.current_track and self.player.current_track.get("id"):
                    is_fav = self.db.is_liked(self.player.current_track.get("id"))
                    fav_btn.label = Content("[Liked]") if is_fav else Content("[Fav]")
                    if is_fav:
                        fav_btn.add_class("is-liked")
                    else:
                        fav_btn.remove_class("is-liked")
                else:
                    fav_btn.label = Content("[Fav]")
                    fav_btn.remove_class("is-liked")
            except Exception:
                pass

            try:
                shuf_btn = self.query_one("#btn-toggle-shuffle", Button)
                shuf_btn.label = Content(f"[Shuf:{'ON' if self.player.shuffle else 'OFF'}]")
                if self.player.shuffle:
                    shuf_btn.add_class("is-active")
                else:
                    shuf_btn.remove_class("is-active")
            except Exception:
                pass

            try:
                rep_btn = self.query_one("#btn-toggle-repeat", Button)
                rep_btn.label = Content(f"[Rep:{self.player.repeat_mode}]")
                rep_btn.remove_class("is-active", "is-one")
                if self.player.repeat_mode == "ONE":
                    rep_btn.add_class("is-one")
                elif self.player.repeat_mode == "ALL":
                    rep_btn.add_class("is-active")
            except Exception:
                pass

            if not status["active"]:
                self.is_loading_track = False
                title_lbl.update("[IDLE] Belum ada lagu yang diputar")
                prog_lbl.update("00:00 [--------------------------------] 00:00")
                stat_lbl.update("STATUS: Ready                    VOL: " + make_vol_bar(status["volume"]))
                try:
                    self.query_one("#btn-play", Button).label = Content("[>]")
                except Exception:
                    pass
                return

            # Check if we transitioned from loading to playing
            if self.is_loading_track:
                if status["time_pos"] > 0:
                    self.is_loading_track = False
                else:
                    # Still loading, animate symbol
                    self._load_symbol_idx += 1
                    frame = self._load_frames[self._load_symbol_idx % len(self._load_frames)]
                    track = self.loading_track_info or {}
                    title_lbl.update(f"[LOAD {frame}] {track.get('title', '')} - {track.get('artist', '')}")
                    dur = track.get("duration", "--:--")
                    prog_lbl.update(f"00:00 [===>----------------------------] {dur}")
                    stat_lbl.update(f"STATUS: Loading {frame}                  VOL: " + make_vol_bar(status["volume"]))
                    try:
                        self.query_one("#btn-play", Button).label = Content(f"[{frame}]")
                    except Exception:
                        pass
                    return

            # Normal active playback
            play_state = "[PAUSE]" if status["paused"] else "[PLAY]"
            title_str = f"{play_state} {status['title']} - {status['artist']}"
            title_lbl.update(title_str)
            try:
                self.query_one("#btn-play", Button).label = Content("[>]") if status["paused"] else Content("[||]")
            except Exception:
                pass

            # Progress bar
            bar_str = make_progress_bar(status["percent"], width=32)
            prog_lbl.update(f"{status['time_str']} {bar_str} {status['dur_str']}")

            # Bottom status
            state_name = "Paused " if status["paused"] else "Playing"
            audio_source = "Offline/Opus" if status.get("is_offline") else "PipeWire/Opus"
            queue_len = len(self.player.queue)
            radio_len = len(self.player.radio_queue) if self.player.autoplay else 0
            q_info = f"QUEUE: {queue_len}"
            if radio_len > 0:
                q_info += f" (+{radio_len} Radio)"
            auto_text = "ON" if self.player.autoplay else "OFF"
            stat_lbl.update(
                f"STATUS: {state_name} ({audio_source})   {q_info}   RADIO: [{auto_text}]   VOL: " + make_vol_bar(status["volume"])
            )
        except Exception:
            pass

    # ---------------- CLEAN SHUTDOWN ----------------

    def action_quit_app(self):
        self._save_current_player_state()
        if self._playback_timer:
            self._playback_timer.stop()
        self.player.close()
        self.exit()
