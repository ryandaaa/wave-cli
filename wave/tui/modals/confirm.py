"""
Confirmation modal dialog screen (Yes/No).
"""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Label


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
