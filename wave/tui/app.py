"""
WaveApp: Core Textual Application.
"""

from pathlib import Path
from typing import Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.renderables import blank
from textual.widgets import Button, Input, Label

import wave.tui.textual_patches  # noqa: F401
from wave.db import Database
from wave.player import Player
from wave.tui.mixins.buttons import ButtonsMixin
from wave.tui.mixins.caching import CachingMixin
from wave.tui.mixins.likes import LikesMixin
from wave.tui.mixins.modes import ModesMixin
from wave.tui.mixins.navigation import NavigationMixin
from wave.tui.mixins.playback import PlaybackMixin
from wave.tui.mixins.playlists import PlaylistsMixin
from wave.tui.mixins.queue_ops import QueueOpsMixin
from wave.tui.mixins.search import SearchMixin
from wave.tui.mixins.sidebar import SidebarMixin
from wave.tui.mixins.ticker import TickerMixin
from wave.tui.mixins.tracklist import TracklistMixin
from wave.util.format import make_vol_bar


class WaveApp(
    NavigationMixin,
    SidebarMixin,
    TracklistMixin,
    SearchMixin,
    PlaybackMixin,
    QueueOpsMixin,
    LikesMixin,
    PlaylistsMixin,
    ModesMixin,
    CachingMixin,
    ButtonsMixin,
    TickerMixin,
    App,
):
    CSS_PATH = Path(__file__).parent / "styles" / "wave.tcss"
    TITLE = "WAVE-CLI"

    # Register mixin @on message handlers with Textual's _MessagePumpMeta
    on_button_click = ButtonsMixin.on_button_click
    on_row_click = TracklistMixin.on_row_click

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
            shuffle=saved_shuffle,
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
            id="top-bar",
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
