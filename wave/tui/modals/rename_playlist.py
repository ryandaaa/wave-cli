"""
Modal screen for renaming an existing playlist.
"""

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


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
