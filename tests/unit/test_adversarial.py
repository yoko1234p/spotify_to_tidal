# tests/unit/test_adversarial.py
# 對抗性測試：驗證 null/missing fields 唔會 crash

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from spotify_to_tidal.sync import (
    simple,
    isrc_match,
    name_match,
    artist_match,
    match,
    _fetch_all_from_spotify_in_chunks,
    get_tracks_from_spotify_playlist,
)
from spotify_to_tidal.tidalapi_patch import add_multiple_tracks_to_playlist


# ==================== simple() null safety ====================

class TestSimpleNullSafety:
    def test_none_input(self):
        assert simple(None) == ""

    def test_empty_string(self):
        assert simple("") == ""

    def test_normal_input(self):
        assert simple("Hello World") == "Hello World"

    def test_with_hyphen(self):
        assert simple("Track Name - Remix") == "Track Name"

    def test_with_brackets(self):
        assert simple("Track Name (feat. Artist)") == "Track Name"

    def test_with_square_brackets(self):
        assert simple("Track Name [Deluxe]") == "Track Name"


# ==================== isrc_match() missing external_ids ====================

class TestIsrcMatchNullSafety:
    def _make_tidal_track(self, isrc="USRC12345678"):
        track = MagicMock()
        track.isrc = isrc
        return track

    def test_missing_external_ids_key(self):
        """spotify track 完全冇 external_ids"""
        tidal = self._make_tidal_track()
        spotify = {"id": "123", "name": "Test"}
        assert isrc_match(tidal, spotify) == False

    def test_empty_external_ids(self):
        """external_ids 係空 dict"""
        tidal = self._make_tidal_track()
        spotify = {"id": "123", "external_ids": {}}
        assert isrc_match(tidal, spotify) == False

    def test_normal_isrc_match(self):
        tidal = self._make_tidal_track("USRC12345678")
        spotify = {"id": "123", "external_ids": {"isrc": "USRC12345678"}}
        assert isrc_match(tidal, spotify) == True

    def test_normal_isrc_no_match(self):
        tidal = self._make_tidal_track("USRC00000000")
        spotify = {"id": "123", "external_ids": {"isrc": "USRC12345678"}}
        assert isrc_match(tidal, spotify) == False


# ==================== name_match() with None name ====================

class TestNameMatchNullSafety:
    def _make_tidal_track(self, name="Test Track", version=None):
        track = MagicMock()
        track.name = name
        track.version = version
        return track

    def test_spotify_name_is_none(self):
        """spotify track name 係 None"""
        tidal = self._make_tidal_track("Test Track")
        spotify = {"name": None, "artists": []}
        assert name_match(tidal, spotify) == False

    def test_both_names_normal(self):
        tidal = self._make_tidal_track("Test Track")
        spotify = {"name": "Test Track", "artists": []}
        assert name_match(tidal, spotify) == True


# ==================== _fetch_all_from_spotify_in_chunks ====================

class TestFetchAllFromSpotify:
    def test_items_with_track_key(self):
        """傳統 API 格式：item['track']"""
        def fetch(offset):
            return {
                "items": [
                    {"track": {"name": "Song A", "id": "1"}},
                    {"track": {"name": "Song B", "id": "2"}},
                ],
                "next": None,
                "total": 2,
                "limit": 100,
            }
        result = asyncio.run(_fetch_all_from_spotify_in_chunks(fetch))
        assert len(result) == 2
        assert result[0]["name"] == "Song A"

    def test_items_with_item_key(self):
        """新 API 格式：item['item']"""
        def fetch(offset):
            return {
                "items": [
                    {"item": {"name": "Song A", "id": "1", "type": "track"}},
                    {"item": {"name": "Song B", "id": "2", "type": "track"}},
                ],
                "next": None,
                "total": 2,
                "limit": 100,
            }
        result = asyncio.run(_fetch_all_from_spotify_in_chunks(fetch))
        assert len(result) == 2
        assert result[0]["name"] == "Song A"

    def test_items_empty_dict(self):
        """API 返空 dict item"""
        def fetch(offset):
            return {
                "items": [{}, {}, {}],
                "next": None,
                "total": 3,
                "limit": 100,
            }
        result = asyncio.run(_fetch_all_from_spotify_in_chunks(fetch))
        assert len(result) == 0

    def test_items_missing_entirely(self):
        """API response 冇 items key"""
        def fetch(offset):
            return {
                "next": None,
                "total": 0,
                "limit": 100,
            }
        result = asyncio.run(_fetch_all_from_spotify_in_chunks(fetch))
        assert len(result) == 0

    def test_mixed_track_and_item_keys(self):
        """混合格式"""
        def fetch(offset):
            return {
                "items": [
                    {"track": {"name": "Old Format", "id": "1"}},
                    {"item": {"name": "New Format", "id": "2"}},
                    {},
                    {"track": None},
                ],
                "next": None,
                "total": 4,
                "limit": 100,
            }
        result = asyncio.run(_fetch_all_from_spotify_in_chunks(fetch))
        assert len(result) == 2
        assert result[0]["name"] == "Old Format"
        assert result[1]["name"] == "New Format"

    def test_track_none_item_exists(self):
        """track=None 但 item 有值"""
        def fetch(offset):
            return {
                "items": [
                    {"track": None, "item": {"name": "Fallback", "id": "1"}},
                ],
                "next": None,
                "total": 1,
                "limit": 100,
            }
        result = asyncio.run(_fetch_all_from_spotify_in_chunks(fetch))
        assert len(result) == 1
        assert result[0]["name"] == "Fallback"


# ==================== add_multiple_tracks_to_playlist fallback ====================

class TestAddMultipleTracksPlaylist:
    def test_batch_success(self):
        """正常 batch add"""
        playlist = MagicMock()
        add_multiple_tracks_to_playlist(playlist, [1, 2, 3, 4, 5], chunk_size=3)
        assert playlist.add.call_count == 2

    def test_batch_fail_fallback_individual(self):
        """batch 失敗，fallback 逐首加"""
        playlist = MagicMock()
        call_count = [0]

        def mock_add(track_ids):
            call_count[0] += 1
            if len(track_ids) > 1:
                raise Exception("412 Precondition Failed")

        playlist.add = mock_add
        playlist._reparse = MagicMock()

        add_multiple_tracks_to_playlist(playlist, [1, 2, 3], chunk_size=3)
        assert call_count[0] == 4

    def test_individual_fail_skips(self, capsys):
        """逐首加都失敗，skip 唔 crash"""
        playlist = MagicMock()

        def mock_add(track_ids):
            raise Exception("Tidal refused")

        playlist.add = mock_add
        playlist._reparse = MagicMock()

        add_multiple_tracks_to_playlist(playlist, [1, 2], chunk_size=2)
        captured = capsys.readouterr()
        assert "Skipping track" in captured.out
        assert "1" in captured.out
        assert "2" in captured.out

    def test_empty_track_list(self):
        """空 list 唔 crash"""
        playlist = MagicMock()
        add_multiple_tracks_to_playlist(playlist, [])
        playlist.add.assert_not_called()


# ==================== get_tracks_from_spotify_playlist filters ====================

class TestGetTracksFilters:
    def test_filters_episodes(self):
        """過濾 podcast episodes"""
        async def _test():
            with patch('spotify_to_tidal.sync.repeat_on_request_error') as mock_repeat:
                mock_repeat.return_value = [
                    {"type": "track", "name": "Song", "id": "1",
                     "album": {"name": "Album", "artists": [{"name": "Artist"}]},
                     "artists": [{"name": "Artist"}]},
                    {"type": "episode", "name": "Podcast", "id": "2",
                     "album": {"name": "Show", "artists": [{"name": "Host"}]},
                     "artists": [{"name": "Host"}]},
                ]
                result = await get_tracks_from_spotify_playlist(
                    MagicMock(), {"name": "Test", "id": "abc"})
                assert len(result) == 1
                assert result[0]["name"] == "Song"
        asyncio.run(_test())

    def test_filters_missing_album(self):
        """過濾冇 album 嘅 track"""
        async def _test():
            with patch('spotify_to_tidal.sync.repeat_on_request_error') as mock_repeat:
                mock_repeat.return_value = [
                    {"type": "track", "name": "No Album", "id": "1",
                     "artists": [{"name": "Artist"}]},
                    {"type": "track", "name": "Good Track", "id": "2",
                     "album": {"name": "Album", "artists": [{"name": "Artist"}]},
                     "artists": [{"name": "Artist"}]},
                ]
                result = await get_tracks_from_spotify_playlist(
                    MagicMock(), {"name": "Test", "id": "abc"})
                assert len(result) == 1
                assert result[0]["name"] == "Good Track"
        asyncio.run(_test())

    def test_filters_none_artist_name(self):
        """過濾 artist name 係 None 嘅 track"""
        async def _test():
            with patch('spotify_to_tidal.sync.repeat_on_request_error') as mock_repeat:
                mock_repeat.return_value = [
                    {"type": "track", "name": "Bad Artist", "id": "1",
                     "album": {"name": "Album", "artists": [{"name": None}]},
                     "artists": [{"name": None}]},
                ]
                result = await get_tracks_from_spotify_playlist(
                    MagicMock(), {"name": "Test", "id": "abc"})
                assert len(result) == 0
        asyncio.run(_test())
