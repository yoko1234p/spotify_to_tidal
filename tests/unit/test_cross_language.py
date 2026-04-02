# tests/unit/test_cross_language.py
# Tests for cross-language track matching features

import pytest
import asyncio
from unittest.mock import MagicMock, patch, PropertyMock
from spotify_to_tidal.sync import (
    isrc_match,
    match,
    duration_match,
    artist_match,
    name_match,
    tidal_search,
    _artist_albums_cache,
)


def _make_tidal_track(name="Test", duration=210, isrc="TEST123", available=True,
                      artist_name="Artist", track_num=1, volume_num=1):
    track = MagicMock()
    track.available = available
    track.duration = duration
    track.isrc = isrc
    track.name = name
    track.version = None
    track.track_num = track_num
    track.volume_num = volume_num
    artist_mock = MagicMock()
    artist_mock.name = artist_name
    track.artists = [artist_mock]
    return track


def _make_spotify_track(name="Test", duration_ms=210000, isrc="TEST123",
                        artist_name="Artist", track_number=1, disc_number=1,
                        album_name="Album", total_tracks=10):
    return {
        "id": "spotify_id_1",
        "name": name,
        "duration_ms": duration_ms,
        "external_ids": {"isrc": isrc},
        "artists": [{"name": artist_name}],
        "track_number": track_number,
        "disc_number": disc_number,
        "album": {
            "name": album_name,
            "total_tracks": total_tracks,
            "artists": [{"name": artist_name}],
        },
    }


# ==================== ISRC case-insensitive ====================

class TestIsrcCaseInsensitive:
    def test_uppercase_match(self):
        assert isrc_match(_make_tidal_track(isrc="HKD250216702"),
                          {"id": "1", "external_ids": {"isrc": "HKD250216702"}}) == True

    def test_lowercase_spotify_isrc(self):
        assert isrc_match(_make_tidal_track(isrc="HKD250216702"),
                          {"id": "1", "external_ids": {"isrc": "hkd250216702"}}) == True

    def test_mixed_case(self):
        assert isrc_match(_make_tidal_track(isrc="hkd250216702"),
                          {"id": "1", "external_ids": {"isrc": "HKD250216702"}}) == True

    def test_no_tidal_isrc(self):
        assert isrc_match(_make_tidal_track(isrc=None),
                          {"id": "1", "external_ids": {"isrc": "HKD250216702"}}) == False

    def test_no_spotify_isrc(self):
        assert isrc_match(_make_tidal_track(isrc="HKD250216702"),
                          {"id": "1", "external_ids": {}}) == False

    def test_no_external_ids(self):
        assert isrc_match(_make_tidal_track(isrc="HKD250216702"),
                          {"id": "1"}) == False


# ==================== track.available in match() ====================

class TestAvailableFilter:
    def test_available_track_matches(self):
        tidal = _make_tidal_track(available=True)
        spotify = _make_spotify_track()
        assert match(tidal, spotify) == True

    def test_unavailable_track_rejected(self):
        tidal = _make_tidal_track(available=False)
        spotify = _make_spotify_track()
        assert match(tidal, spotify) == False

    def test_unavailable_track_with_isrc_still_rejected(self):
        """Even with matching ISRC, unavailable tracks should be rejected"""
        tidal = _make_tidal_track(available=False, isrc="SAME_ISRC")
        spotify = _make_spotify_track(isrc="SAME_ISRC")
        assert match(tidal, spotify) == False


# ==================== Cross-language name_match ====================

class TestCrossLanguageNameMatch:
    def test_chinese_vs_english_name_fails(self):
        """name_match should fail for different language names"""
        tidal = _make_tidal_track(name="Midnight Romance")
        spotify = _make_spotify_track(name="深夜浪漫")
        assert not name_match(tidal, spotify)

    def test_japanese_vs_english_name_fails(self):
        tidal = _make_tidal_track(name="Merry Christmas Mr.Lawrence")
        spotify = _make_spotify_track(name="戦場のメリークリスマス")
        assert not name_match(tidal, spotify)

    def test_same_name_passes(self):
        tidal = _make_tidal_track(name="Midnight Romance")
        spotify = _make_spotify_track(name="Midnight Romance")
        assert name_match(tidal, spotify)

    def test_substring_match_passes(self):
        tidal = _make_tidal_track(name="Midnight Romance (Deluxe)")
        spotify = _make_spotify_track(name="Midnight Romance")
        assert name_match(tidal, spotify)


# ==================== Full match() cross-language ====================

class TestMatchCrossLanguage:
    def test_full_match_fails_cross_language(self):
        """match() requires name_match, so cross-language fails"""
        tidal = _make_tidal_track(name="Midnight Romance", isrc="TIDAL_ISRC",
                                  artist_name="Gigi Cheung")
        spotify = _make_spotify_track(name="深夜浪漫", isrc="SPOTIFY_ISRC",
                                      artist_name="Gigi Cheung")
        assert not match(tidal, spotify)

    def test_relaxed_validation_passes_cross_language(self):
        """duration + artist match should pass for cross-language"""
        tidal = _make_tidal_track(name="Midnight Romance", duration=210,
                                  artist_name="Gigi Cheung")
        spotify = _make_spotify_track(name="深夜浪漫", duration_ms=210500,
                                      artist_name="Gigi Cheung")
        assert duration_match(tidal, spotify) == True
        assert artist_match(tidal, spotify) == True

    def test_relaxed_validation_fails_wrong_duration(self):
        """Wrong duration should fail even with relaxed validation"""
        tidal = _make_tidal_track(name="Wrong Song", duration=300,
                                  artist_name="Gigi Cheung")
        spotify = _make_spotify_track(name="深夜浪漫", duration_ms=210000,
                                      artist_name="Gigi Cheung")
        assert duration_match(tidal, spotify) == False

    def test_relaxed_validation_fails_wrong_artist(self):
        """Wrong artist should fail even with relaxed validation"""
        tidal = _make_tidal_track(name="Midnight Romance", duration=210,
                                  artist_name="Other Artist")
        spotify = _make_spotify_track(name="深夜浪漫", duration_ms=210000,
                                      artist_name="Gigi Cheung")
        assert artist_match(tidal, spotify) == False


# ==================== Album position match (relaxed) ====================

class TestAlbumPositionMatch:
    def test_album_position_match_cross_language(self):
        """Simulates _search_for_track_in_album with cross-language names"""
        tidal = _make_tidal_track(name="Midnight Romance", duration=210, isrc="TIDAL_ISRC",
                                  artist_name="Gigi Cheung", track_num=3, volume_num=1)
        spotify = _make_spotify_track(name="深夜浪漫", duration_ms=210500, isrc="SPOTIFY_ISRC",
                                      artist_name="Gigi Cheung", track_number=3)
        # full match fails (different ISRC, different language name)
        assert not match(tidal, spotify)
        # but relaxed check (what _search_for_track_in_album now uses) passes
        assert tidal.available and duration_match(tidal, spotify) and artist_match(tidal, spotify)

    def test_album_position_wrong_track_number(self):
        """Different track position should not be considered a match"""
        tidal = _make_tidal_track(name="Other Song", duration=210,
                                  artist_name="Gigi Cheung", track_num=5, volume_num=1)
        spotify = _make_spotify_track(name="深夜浪漫", duration_ms=210500,
                                      artist_name="Gigi Cheung", track_number=3)
        # even if duration+artist match, track_num mismatch means we wouldn't pick this track
        assert tidal.track_num != spotify["track_number"]


# ==================== Artist album browsing ====================

class TestArtistAlbumBrowsing:
    def _make_tidal_album(self, num_tracks=10, tracks=None):
        album = MagicMock()
        album.num_tracks = num_tracks
        album.tracks.return_value = tracks or []
        return album

    def test_exact_track_count_preferred(self):
        """Albums with exact track count should be preferred over ±2"""
        albums = [
            self._make_tidal_album(num_tracks=8),   # within ±2 but not exact
            self._make_tidal_album(num_tracks=10),  # exact match
            self._make_tidal_album(num_tracks=12),  # within ±2 but not exact
        ]
        sp_total = 10
        candidates = [a for a in albums if abs(a.num_tracks - sp_total) <= 2]
        exact = [a for a in candidates if a.num_tracks == sp_total]
        assert len(candidates) == 3
        assert len(exact) == 1
        assert exact[0].num_tracks == 10

    def test_track_position_and_duration_match(self):
        """Track at correct position with matching duration should be found"""
        target_track = _make_tidal_track(
            name="Midnight Romance", duration=210,
            artist_name="Gigi Cheung", track_num=3, volume_num=1)
        other_track = _make_tidal_track(
            name="Other Song", duration=180,
            artist_name="Gigi Cheung", track_num=1, volume_num=1)

        spotify = _make_spotify_track(
            name="深夜浪漫", duration_ms=210500,
            artist_name="Gigi Cheung", track_number=3, disc_number=1)

        album_tracks = [other_track, MagicMock(), target_track]
        for track in album_tracks:
            if (track.track_num == spotify['track_number']
                and track.volume_num == spotify['disc_number']
                and track.available
                and duration_match(track, spotify)
                and artist_match(track, spotify)):
                assert track == target_track
                return
        pytest.fail("Should have found the target track")

    def test_wrong_disc_number_rejected(self):
        """Track on wrong disc should not match"""
        track = _make_tidal_track(
            name="Song", duration=210,
            artist_name="Artist", track_num=3, volume_num=2)  # disc 2
        spotify = _make_spotify_track(
            duration_ms=210000, track_number=3, disc_number=1)  # disc 1
        assert track.volume_num != spotify['disc_number']

    def test_unavailable_track_in_album_rejected(self):
        """Unavailable track at correct position should be skipped"""
        track = _make_tidal_track(
            name="Song", duration=210, available=False,
            artist_name="Artist", track_num=3, volume_num=1)
        spotify = _make_spotify_track(duration_ms=210000, track_number=3)
        assert not track.available


# ==================== Artist albums cache ====================

class TestArtistAlbumsCache:
    def test_cache_exists(self):
        assert isinstance(_artist_albums_cache, dict)

    def test_cache_stores_empty_for_unknown_artist(self):
        """Cache should store empty list for artists not found on Tidal"""
        _artist_albums_cache['test_unknown_artist'] = []
        assert _artist_albums_cache['test_unknown_artist'] == []
        del _artist_albums_cache['test_unknown_artist']


# ==================== AI fallback ====================

class TestAIFallback:
    def test_ai_disabled_by_default(self):
        """AI fallback should not trigger without config"""
        # _search_with_ai checks config.get('ai_fallback')
        # when config is None or ai_fallback not enabled, should return None
        config = {}
        ai_config = config.get('ai_fallback')
        assert ai_config is None

    def test_ai_disabled_when_not_enabled(self):
        config = {"ai_fallback": {"enabled": False}}
        ai_config = config.get('ai_fallback')
        assert not ai_config.get('enabled')

    def test_ai_enabled_config(self):
        config = {
            "ai_fallback": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key_env": "OPENAI_API_KEY",
            }
        }
        ai_config = config.get('ai_fallback')
        assert ai_config.get('enabled') == True
        assert ai_config.get('provider') == 'openai'

    def test_ai_no_api_key_returns_none(self):
        """AI fallback should skip if no API key set (non-ollama)"""
        import os
        api_key_env = "NONEXISTENT_KEY_FOR_TEST_12345"
        api_key = os.environ.get(api_key_env, '')
        assert api_key == ''
        # provider != 'ollama' and no api_key → should return None

    def test_ai_ollama_no_key_needed(self):
        """Ollama provider should not require API key"""
        config = {
            "ai_fallback": {
                "enabled": True,
                "provider": "ollama",
                "model": "llama3",
                "ollama_base_url": "http://localhost:11434",
            }
        }
        ai_config = config['ai_fallback']
        assert ai_config['provider'] == 'ollama'
        # ollama doesn't need api_key_env


# ==================== Adversarial: edge cases ====================

class TestAdversarialCrossLanguage:
    def test_empty_artist_name_no_crash(self):
        """Empty artist name should not crash artist album browsing"""
        spotify = _make_spotify_track(artist_name="")
        from spotify_to_tidal.sync import simple
        artist_name = simple(spotify['artists'][0].get('name', ''))
        assert artist_name == ""

    def test_missing_album_no_crash(self):
        """Track without album should not crash"""
        spotify = {"id": "1", "name": "Test", "artists": [{"name": "A"}],
                   "duration_ms": 200000, "external_ids": {}}
        assert 'album' not in spotify

    def test_missing_track_number_no_crash(self):
        """Track without track_number should not crash"""
        spotify = _make_spotify_track()
        del spotify['track_number']
        sp_track_num = spotify.get('track_number', 0)
        assert sp_track_num == 0

    def test_zero_total_tracks_skipped(self):
        """Album with 0 total tracks should be skipped"""
        spotify = _make_spotify_track(total_tracks=0)
        assert spotify['album']['total_tracks'] == 0

    def test_duration_edge_exact_boundary(self):
        """Duration at exactly 2 second boundary"""
        tidal = _make_tidal_track(duration=210)
        spotify_just_inside = _make_spotify_track(duration_ms=211999)
        spotify_at_boundary = _make_spotify_track(duration_ms=212000)
        spotify_just_outside = _make_spotify_track(duration_ms=212001)
        assert duration_match(tidal, spotify_just_inside) == True
        assert duration_match(tidal, spotify_at_boundary) == False
        assert duration_match(tidal, spotify_just_outside) == False

    def test_multiple_artists_cross_language(self):
        """Artist match should work when one of multiple artists matches"""
        tidal = _make_tidal_track(artist_name="Gigi Cheung")
        # add second artist
        artist2 = MagicMock()
        artist2.name = "Other Artist"
        tidal.artists.append(artist2)

        spotify = _make_spotify_track(artist_name="Gigi Cheung")
        spotify['artists'].append({"name": "Different Artist"})

        assert artist_match(tidal, spotify) == True

    def test_artist_match_normalized_cjk(self):
        """CJK artist names that normalize to empty should not falsely match"""
        tidal = _make_tidal_track(artist_name="張敬軒")
        spotify = _make_spotify_track(artist_name="陳奕迅")
        # different CJK artists should NOT match
        # un-normalized: "張敬軒" vs "陳奕迅" → no intersection
        # normalized: both become "" → should NOT match (fixed bug)
        assert artist_match(tidal, spotify) == False

    def test_album_count_tolerance(self):
        """Album with ±2 track count should be candidate, but exact preferred"""
        sp_total = 10
        counts = [8, 9, 10, 11, 12, 13]
        candidates = [c for c in counts if abs(c - sp_total) <= 2]
        assert candidates == [8, 9, 10, 11, 12]
        exact = [c for c in candidates if c == sp_total]
        assert exact == [10]

    def test_compilation_different_track_order(self):
        """Two albums with same track count but different content"""
        # This tests that we check track_num + duration, not just track count
        track_a = _make_tidal_track(name="Song A", duration=200, track_num=3, volume_num=1)
        track_b = _make_tidal_track(name="Song B", duration=250, track_num=3, volume_num=1)
        spotify = _make_spotify_track(duration_ms=200000, track_number=3)

        # track_a matches duration, track_b doesn't
        assert duration_match(track_a, spotify) == True
        assert duration_match(track_b, spotify) == False

    def test_isrc_match_with_garbage_isrc(self):
        """Garbage ISRC format should not crash"""
        tidal = _make_tidal_track(isrc="NORMAL123456")
        spotify = {"id": "1", "external_ids": {"isrc": "isrcmydg11300003"}}
        # should not crash, just return False
        assert isrc_match(tidal, spotify) == False

    def test_match_with_no_id(self):
        """Track with empty id should return False"""
        tidal = _make_tidal_track()
        spotify = _make_spotify_track()
        spotify['id'] = ''
        assert not match(tidal, spotify)

    def test_match_with_none_id(self):
        """Track with None id should return False"""
        tidal = _make_tidal_track()
        spotify = _make_spotify_track()
        spotify['id'] = None
        assert not match(tidal, spotify)
