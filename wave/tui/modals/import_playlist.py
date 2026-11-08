"""
Modal screen for importing a YouTube playlist via URL.
"""

from typing import Dict, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


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
