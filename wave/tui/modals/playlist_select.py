"""
Modal screen for selecting a playlist to add a track to.
"""

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Label


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
