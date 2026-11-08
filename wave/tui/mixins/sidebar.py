"""
Sidebar navigation counts and playlist listing mixin for WaveApp.
"""
from textual import work
from textual.containers import Vertical
from textual.widgets import Button

class SidebarMixin:

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
