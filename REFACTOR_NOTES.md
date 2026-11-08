# Refactoring Notes: wave-cli

## Baseline Test Suite

- **Date / Timestamp**: 2026-11-08T02:07:03Z
- **Environment**: Linux x86_64, Python 3.13.5, pytest 9.2.0, pluggy 1.7.0, mpv v0.40.0
- **Total tests collected**: 132
- **Passed**: 112
- **Failed**: 20
- **Execution duration**: 7.23s

### List of Pre-existing Baseline Failing Tests (20)
1. `tests/e2e/test_tier1_feature_coverage.py::test_format_duration_edge_cases`
2. `tests/e2e/test_tier1_feature_coverage.py::test_single_video_url_search_handling`
3. `tests/e2e/test_tier1_feature_coverage.py::test_search_query_caching`
4. `tests/e2e/test_tier1_feature_coverage.py::test_help_modal_and_toast_ascii`
5. `tests/e2e/test_tier1_feature_coverage.py::test_cli_help_flag`
6. `tests/e2e/test_tier1_feature_coverage.py::test_cli_version_flag`
7. `tests/e2e/test_tier2_boundary_corner.py::test_invalid_and_malformed_urls`
8. `tests/e2e/test_tier2_boundary_corner.py::test_duration_boundary_values`
9. `tests/e2e/test_tier2_boundary_corner.py::test_missing_and_dead_socket_resilience`
10. `tests/e2e/test_tier3_cross_feature.py::test_full_streaming_user_journey`
11. `tests/e2e/test_tier3_cross_feature.py::test_playback_queue_and_history_lifecycle`
12. `tests/e2e/test_tier3_cross_feature.py::test_socket_failure_and_recovery_loop`
13. `tests/test_adversarial_database.py::TestConcurrencyStress::test_concurrent_writes_same_playlist`
14. `tests/test_adversarial_database.py::TestConcurrencyStress::test_concurrent_toggle_liked`
15. `tests/test_adversarial_database.py::TestConcurrencyStress::test_concurrent_queue_writes_duplicate_positions`
16. `tests/test_adversarial_database.py::TestEdgeCasesAndExtremePayloads::test_malformed_and_missing_keys_in_track_dicts`
17. `tests/test_adversarial_database.py::TestEdgeCasesAndExtremePayloads::test_none_metadata_fields_unhandled_integrity_error`
18. `tests/test_adversarial_m1_2.py::test_move_playlist_track_out_of_bounds_identical_indices`
19. `tests/test_adversarial_m1_2.py::test_move_queue_track_out_of_bounds_identical_indices`
20. `tests/test_adversarial_m1_2.py::test_migration_v1_missing_created_at_in_playlists`

## Baseline Smoke Test Output

Command:
```bash
python main.py --version
```

Output:
```
wave-cli v0.2.0
```

Exit code: `0`

---

## Bugs noticed (not fixed)

The following bugs were observed during baseline survey (preserved per Rule R1 - pure move-and-rename refactor):
1. **`format_duration(0)` returns `'--:--'`**: `audio_cache.py:format_duration` formats `<= 0` as `'--:--'` instead of `'00:00'`.
2. **Single video search without `entries`**: `search_youtube` in `search.py` returns empty list `[]` when `yt-dlp` returns a direct video object instead of an `entries` dictionary.
3. **No in-memory LRU search cache**: Repeated searches trigger duplicate `yt-dlp` subprocess invocations.
4. **Boundary check in `move_queue_track(0, 0)` and `move_playlist_track(0, 0)`**: Identical indices return `True` early before validating queue/playlist length or bounds against an empty list.
5. **v1 database migration without `created_at`**: `_migrate_to_v2` in `database.py` executes SQL querying `COALESCE(created_at, CURRENT_TIMESTAMP)` which fails if the legacy table schema did not include `created_at`.
6. **SQLite concurrent write locks**: Concurrency stress tests experience locking errors under simultaneous multi-threaded writes.
7. **`search_and_populate` not defined on `WaveApp`**: In `on_mount`, when `initial_query` is provided, `self.search_and_populate(self.initial_query)` is called, but no such method was implemented in monolithic `tui.py`.
8. **Standard library `wave.py` naming collision**: Package name `wave` shares the name of Python's built-in standard library module `/usr/lib/python3.x/wave.py`. Within the repo or when packaged into standalone binary (`dist/wave`), the local package takes precedence. In environments where the package is installed to `site-packages` without `PYTHONPATH`, Python standard library resolves before `site-packages`. Exporting `PYTHONPATH` resolves console scripts.

---

## Final Test Suite Verification

- **Total tests collected**: 132
- **Passed**: 112 (100% baseline parity)
- **Failed**: 20 (identical pre-existing failures)
- **Regressions**: 0
- **Compile check (`python -m compileall -q wave`)**: 0 errors
- **Headless Textual Pilot test**: `mounted OK`
- **Smoke test (`python main.py --version`)**: `wave-cli v0.2.0`

## Largest Remaining Files & Line Counts

All 44 `.py` files in `wave/` are strictly under the 250-line limit:

| File | Lines |
|---|---|
| `wave/tui/app.py` | 230 |
| `wave/db/playlist_tracks.py` | 218 |
| `wave/player/ipc.py` | 207 |
| `wave/tui/mixins/navigation.py` | 183 |
| `wave/db/migrations.py` | 177 |
| `wave/tui/mixins/playback.py` | 170 |
| `wave/db/queue.py` | 158 |
| `wave/tui/mixins/tracklist.py` | 155 |
| `wave/db/liked.py` | 150 |
| `wave/db/schema.py` | 148 |

---

## MRO check

Verified that `WaveApp.mro()` does not alter which implementation of any method wins.
All 69 methods across the 12 mixins are pairwise disjoint; zero method shadowing exists.

### Class Hierarchy & MRO Sequence

```python
WaveApp.mro() = [
    WaveApp,  # from wave.tui.app
    NavigationMixin,  # from wave.tui.mixins.navigation
    SidebarMixin,  # from wave.tui.mixins.sidebar
    TracklistMixin,  # from wave.tui.mixins.tracklist
    SearchMixin,  # from wave.tui.mixins.search
    PlaybackMixin,  # from wave.tui.mixins.playback
    QueueOpsMixin,  # from wave.tui.mixins.queue_ops
    LikesMixin,  # from wave.tui.mixins.likes
    PlaylistsMixin,  # from wave.tui.mixins.playlists
    ModesMixin,  # from wave.tui.mixins.modes
    CachingMixin,  # from wave.tui.mixins.caching
    ButtonsMixin,  # from wave.tui.mixins.buttons
    TickerMixin,  # from wave.tui.mixins.ticker
    App,  # from textual.app
    Generic,  # from typing
    DOMNode,  # from textual.dom
    MessagePump,  # from textual.message_pump
    object,  # from builtins
]
```

### Mixin Method Distribution

| Mixin Class | Method Count | Disjoint | Methods |
|---|---|---|---|
| `NavigationMixin` | 10 | Yes | `_render_view_actions`, `_set_active_nav`, `_set_active_nav_playlist`, `_update_view_header`, `action_nav_history`, `action_nav_liked`, `action_nav_playlist`, `action_nav_queue`, `action_nav_radio`, `action_nav_search` |
| `SidebarMixin` | 3 | Yes | `_refresh_playlists_sidebar`, `_update_playlists_sidebar`, `_update_sidebar_counts` |
| `TracklistMixin` | 10 | Yes | `_get_active_list`, `_populate_table`, `_refresh_current_view`, `_render_tracks`, `_select_row`, `_update_row_cache_states`, `_update_row_playing_states`, `action_cursor_down`, `action_cursor_up`, `on_row_click` |
| `SearchMixin` | 7 | Yes | `_fetch_extended_search`, `_tick_search_spinner`, `action_escape_focus`, `action_focus_search`, `import_youtube_playlist`, `on_input_submitted`, `perform_search` |
| `PlaybackMixin` | 13 | Yes | `_play_next_at_index`, `_play_track`, `_play_track_at_index`, `_save_current_player_state`, `action_next_track`, `action_play_next_item`, `action_play_selected`, `action_prev_track`, `action_seek_backward`, `action_seek_forward`, `action_toggle_pause`, `action_vol_down`, `action_vol_up` |
| `QueueOpsMixin` | 6 | Yes | `_add_to_queue_at_index`, `action_add_queue`, `action_clear_current_view`, `action_delete_item`, `action_move_track_down`, `action_move_track_up` |
| `LikesMixin` | 3 | Yes | `_toggle_like_at_index`, `action_toggle_like`, `action_toggle_like_now_playing` |
| `PlaylistsMixin` | 7 | Yes | `_confirm_delete_playlist`, `_open_playlist_menu_at_index`, `_show_playlist_modal_for_track`, `action_create_new_playlist`, `action_import_playlist`, `action_open_playlist_menu`, `action_rename_current_playlist` |
| `ModesMixin` | 4 | Yes | `_refresh_radio_recommendations`, `action_toggle_autoplay`, `action_toggle_repeat`, `action_toggle_shuffle` |
| `CachingMixin` | 2 | Yes | `_auto_cache_track`, `_download_tracks_batch` |
| `ButtonsMixin` | 1 | Yes | `on_button_click` |
| `TickerMixin` | 3 | Yes | `_update_player_display_loading`, `action_quit_app`, `tick_playback` |
| **Total Mixin Methods** | **69** | **0 Conflicts** | All 12 mixins strictly disjoint |

---

## Functions still > 40 lines

The following 21 functions in the baseline codebase exceed 40 lines. Per Ground Rule R1, existing functions longer than 40 lines will be moved verbatim without breaking logic:

| File | Function | Lines | Total Lines |
|---|---|---|---|
| `search.py` | `fetch_youtube_playlist` | 66–119 | 54 |
| `search.py` | `search_youtube` | 122–177 | 56 |
| `search.py` | `fetch_radio_mix` | 180–239 | 60 |
| `audio_cache.py` | `download_track_audio` | 47–92 | 46 |
| `player.py` | `send_command` | 114–174 | 61 |
| `player.py` | `get_status` | 352–429 | 78 |
| `database.py` | `__init__` | 19–64 | 46 |
| `database.py` | `_connection` | 76–120 | 45 |
| `database.py` | `_create_v2_fresh_schema` | 196–292 | 97 |
| `database.py` | `_migrate_to_v2` | 294–448 | 155 |
| `database.py` | `add_liked` | 452–503 | 52 |
| `database.py` | `add_to_playlist` | 687–742 | 56 |
| `database.py` | `add_tracks_to_playlist` | 744–794 | 51 |
| `database.py` | `move_playlist_track` | 826–868 | 43 |
| `database.py` | `get_player_state` | 1075–1129 | 55 |
| `database.py` | `add_history` | 1133–1192 | 60 |
| `tui.py` | `compose` | 435–516 | 82 |
| `tui.py` | `_render_view_actions` | 648–696 | 49 |
| `tui.py` | `action_toggle_like_now_playing` | 1472–1513 | 42 |
| `tui.py` | `on_button_click` | 1534–1638 | 105 |
| `tui.py` | `tick_playback` | 1721–1828 | 108 |

---

## Final tree

```
wave/
├── __init__.py
├── __main__.py
├── cli.py
├── paths.py
├── cache/
│   ├── __init__.py
│   └── audio_cache.py
├── db/
│   ├── __init__.py
│   ├── connection.py
│   ├── history.py
│   ├── liked.py
│   ├── migrations.py
│   ├── playlist_tracks.py
│   ├── playlists.py
│   ├── queue.py
│   ├── schema.py
│   └── state.py
├── player/
│   ├── __init__.py
│   ├── ipc.py
│   ├── modes.py
│   ├── playback.py
│   ├── queue.py
│   └── status.py
├── tui/
│   ├── __init__.py
│   ├── app.py
│   ├── textual_patches.py
│   ├── mixins/
│   │   ├── __init__.py
│   │   ├── buttons.py
│   │   ├── caching.py
│   │   ├── likes.py
│   │   ├── modes.py
│   │   ├── navigation.py
│   │   ├── playback.py
│   │   ├── playlists.py
│   │   ├── queue_ops.py
│   │   ├── search.py
│   │   ├── sidebar.py
│   │   ├── ticker.py
│   │   └── tracklist.py
│   ├── modals/
│   │   ├── __init__.py
│   │   ├── confirm.py
│   │   ├── import_playlist.py
│   │   ├── new_playlist.py
│   │   ├── playlist_select.py
│   │   └── rename_playlist.py
│   ├── styles/
│   │   └── wave.tcss
│   └── widgets/
│       ├── __init__.py
│       └── track_row.py
├── util/
│   ├── __init__.py
│   └── format.py
└── youtube/
    ├── __init__.py
    ├── binary.py
    ├── playlist.py
    ├── radio.py
    └── search.py
```

---

## build_binary.sh diff

`build_binary.sh` is an environment wrapper that executes `scripts/build_release.py`. It contains no references to old module paths or `.tcss` locations and was left unmodified per Ground Rule R4.

The PyInstaller bundle data path was updated in `scripts/build_release.py`:
```diff
--- a/scripts/build_release.py
+++ b/scripts/build_release.py
@@ -55,3 +55,5 @@
     # 2. Determine separator and PyInstaller arguments
     sep = ";" if sys.platform == "win32" else ":"
-    tcss_path = f"wave.tcss{sep}."
+    tcss_src = os.path.join("wave", "tui", "styles", "wave.tcss")
+    tcss_dst = os.path.join("wave", "tui", "styles")
+    tcss_path = f"{tcss_src}{sep}{tcss_dst}"
```
