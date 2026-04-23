#!/usr/bin/env python3

import asyncio
from .cache import failure_cache, track_match_cache
import datetime
from difflib import SequenceMatcher
from functools import partial
from typing import Callable, List, Sequence, Set, Mapping
import math
import os
import requests
import sys
import spotipy
import threading
import tidalapi
from .tidalapi_patch import add_multiple_tracks_to_playlist, clear_tidal_playlist, get_all_favorites, get_all_playlists, get_all_playlist_tracks
import time
from tqdm.asyncio import tqdm as atqdm
from tqdm import tqdm
import traceback
import unicodedata

from .type import spotify as t_spotify

# in-memory cache for artist albums to avoid repeated API calls
_artist_albums_cache: dict[str, list] = {}

# lock to serialize AI API calls and avoid rate limiting
_ai_lock = threading.Lock()
# lock to protect artist albums cache from concurrent access
_artist_cache_lock = threading.Lock()

def normalize(s) -> str:
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('ascii')

def simple(input_string: str | None) -> str:
    if not input_string:
        return ""
    # only take the first part of a string before any hyphens or brackets to account for different versions
    return input_string.split('-')[0].strip().split('(')[0].strip().split('[')[0].strip()

def isrc_match(tidal_track: tidalapi.Track, spotify_track) -> bool:
    external_ids = spotify_track.get("external_ids", {})
    if "isrc" in external_ids and tidal_track.isrc:
        return tidal_track.isrc.upper() == external_ids["isrc"].upper()
    return False

def duration_match(tidal_track: tidalapi.Track, spotify_track, tolerance=2) -> bool:
    # the duration of the two tracks must be the same to within 2 seconds
    return abs(tidal_track.duration - spotify_track['duration_ms']/1000) < tolerance

def name_match(tidal_track, spotify_track) -> bool:
    if not spotify_track.get('name'):
        return False
    def exclusion_rule(pattern: str, tidal_track: tidalapi.Track, spotify_track: t_spotify.SpotifyTrack):
        spotify_has_pattern = pattern in (spotify_track.get('name') or '').lower()
        tidal_has_pattern = pattern in tidal_track.name.lower() or (not tidal_track.version is None and (pattern in tidal_track.version.lower()))
        return spotify_has_pattern != tidal_has_pattern

    # handle some edge cases
    if exclusion_rule("instrumental", tidal_track, spotify_track): return False
    if exclusion_rule("acapella", tidal_track, spotify_track): return False
    if exclusion_rule("remix", tidal_track, spotify_track): return False

    # the simplified version of the Spotify track name must be a substring of the Tidal track name
    # Try with both un-normalized and then normalized
    simple_spotify_track = simple((spotify_track.get('name') or '').lower()).split('feat.')[0].strip()
    if not simple_spotify_track:
        return False
    normalized_spotify = normalize(simple_spotify_track)
    normalized_tidal = normalize(tidal_track.name.lower())
    return simple_spotify_track in tidal_track.name.lower() or (normalized_spotify and normalized_spotify in normalized_tidal)

def artist_match(tidal: tidalapi.Track | tidalapi.Album, spotify) -> bool:
    def split_artist_name(artist: str) -> Sequence[str]:
       if '&' in artist:
           return artist.split('&')
       elif ',' in artist:
           return artist.split(',')
       else:
           return [artist]

    def get_tidal_artists(tidal: tidalapi.Track | tidalapi.Album, do_normalize=False) -> Set[str]:
        result: list[str] = []
        for artist in tidal.artists:
            if do_normalize:
                artist_name = normalize(artist.name)
            else:
                artist_name = artist.name
            result.extend(split_artist_name(artist_name))
        return set([simple(x.strip().lower()) for x in result])

    def get_spotify_artists(spotify, do_normalize=False) -> Set[str]:
        result: list[str] = []
        for artist in spotify['artists']:
            if do_normalize:
                artist_name = normalize(artist['name'])
            else:
                artist_name = artist['name']
            result.extend(split_artist_name(artist_name))
        return set([simple(x.strip().lower()) for x in result])
    # There must be at least one overlapping artist between the Tidal and Spotify track
    # Try with both un-normalized and then normalized
    if get_tidal_artists(tidal).intersection(get_spotify_artists(spotify)) != set():
        return True
    normalized_tidal = get_tidal_artists(tidal, True) - {''}
    normalized_spotify = get_spotify_artists(spotify, True) - {''}
    if normalized_tidal and normalized_spotify:
        return normalized_tidal.intersection(normalized_spotify) != set()
    return False

def match(tidal_track, spotify_track) -> bool:
    if not spotify_track['id']: return False
    if not tidal_track.available: return False
    return isrc_match(tidal_track, spotify_track) or (
        duration_match(tidal_track, spotify_track)
        and name_match(tidal_track, spotify_track)
        and artist_match(tidal_track, spotify_track)
    )

def test_album_similarity(spotify_album, tidal_album, threshold=0.6):
    return SequenceMatcher(None, simple(spotify_album['name']), simple(tidal_album.name)).ratio() >= threshold and artist_match(tidal_album, spotify_album)

async def tidal_search(spotify_track, rate_limiter, tidal_session: tidalapi.Session, config: dict = None) -> tidalapi.Track | None:
    def _search_by_isrc():
        # ISRC is language-agnostic, try this first
        isrc = spotify_track.get('external_ids', {}).get('isrc')
        if not isrc:
            return None
        try:
            tracks = tidal_session.get_tracks_by_isrc(isrc.upper())
            for track in tracks:
                if track.available and duration_match(track, spotify_track):
                    failure_cache.remove_match_failure(spotify_track['id'])
                    return track
        except Exception as e:
            if 'ObjectNotFound' not in type(e).__name__ and 'InvalidISRC' not in type(e).__name__:
                print(f"  [ISRC lookup error] {e}")
        return None

    def _search_for_track_in_album():
        # search for album name and first album artist
        if 'album' in spotify_track and 'artists' in spotify_track['album'] and len(spotify_track['album']['artists']):
            query = simple(spotify_track['album']['name']) + " " + simple(spotify_track['album']['artists'][0]['name'])
            album_result = tidal_session.search(query, models=[tidalapi.album.Album])
            for album in album_result['albums']:
                if album.num_tracks >= spotify_track['track_number'] and test_album_similarity(spotify_track['album'], album):
                    album_tracks = album.tracks()
                    if len(album_tracks) < spotify_track['track_number']:
                        assert( not len(album_tracks) == album.num_tracks ) # incorrect metadata :(
                        continue
                    track = album_tracks[spotify_track['track_number'] - 1]
                    # relaxed validation: album similarity + track position already confirmed,
                    # so only check duration + artist (skip name_match for cross-language support)
                    if track.available and duration_match(track, spotify_track) and artist_match(track, spotify_track):
                        failure_cache.remove_match_failure(spotify_track['id'])
                        return track

    def _search_for_standalone_track():
        # if album search fails then search for track name and first artist
        query = simple(spotify_track['name']) + ' ' + simple(spotify_track['artists'][0]['name'])
        for track in tidal_session.search(query, models=[tidalapi.media.Track])['tracks']:
            if match(track, spotify_track):
                failure_cache.remove_match_failure(spotify_track['id'])
                return track

    def _search_by_artist_albums():
        # fallback: browse artist's albums on Tidal, match by album track count + track position + duration
        if 'album' not in spotify_track or 'artists' not in spotify_track or not spotify_track['artists']:
            return None
        artist_name = simple(spotify_track['artists'][0].get('name', ''))
        if not artist_name:
            return None
        sp_album = spotify_track['album']
        sp_total_tracks = sp_album.get('total_tracks', 0)
        sp_track_num = spotify_track.get('track_number', 0)
        sp_disc_num = spotify_track.get('disc_number', 1)
        if not sp_total_tracks or not sp_track_num:
            return None

        # check cache first (thread-safe)
        cache_key = artist_name.lower().strip()
        with _artist_cache_lock:
            if cache_key not in _artist_albums_cache:
                # search for artist on Tidal
                artist_results = tidal_session.search(artist_name, models=[tidalapi.artist.Artist])
                if not artist_results['artists']:
                    _artist_albums_cache[cache_key] = []
                    return None
                tidal_artist = artist_results['artists'][0]
                # get all albums + singles
                try:
                    albums = tidal_artist.get_albums() + tidal_artist.get_ep_singles()
                except Exception as e:
                    print(f"  [Artist album lookup failed] {e}")
                    albums = []
                _artist_albums_cache[cache_key] = albums

        albums = _artist_albums_cache[cache_key]
        if not albums:
            return None

        # filter candidate albums by track count (allow ±2 for deluxe editions)
        candidates = [a for a in albums if abs(a.num_tracks - sp_total_tracks) <= 2]
        # prefer exact match
        exact = [a for a in candidates if a.num_tracks == sp_total_tracks]
        if exact:
            candidates = exact

        for album in candidates:
            try:
                album_tracks = album.tracks()
            except Exception:
                continue
            for track in album_tracks:
                if (track.track_num == sp_track_num
                    and track.volume_num == sp_disc_num
                    and track.available
                    and duration_match(track, spotify_track)
                    and artist_match(track, spotify_track)):
                    print(f"  [Artist album match] '{spotify_track.get('name')}' -> '{track.name}' by {artist_name}")
                    failure_cache.remove_match_failure(spotify_track['id'])
                    return track
        return None

    def _search_with_ai():
        # optional AI fallback: ask LLM for alternative track name, then search Tidal
        # serialize AI calls to avoid rate limiting
        with _ai_lock:
            return _search_with_ai_inner()

    def _search_with_ai_inner():
        ai_config = config.get('ai_fallback') if config else None
        if not ai_config or not ai_config.get('enabled'):
            return None
        track_name = spotify_track.get('name', '')
        artist_name = spotify_track['artists'][0].get('name', '') if spotify_track.get('artists') else ''
        if not track_name or not artist_name:
            return None

        provider = ai_config.get('provider', 'openai')
        model = ai_config.get('model', 'gpt-4o-mini')
        api_key = ai_config.get('api_key', '')
        if not api_key:
            api_key_env = ai_config.get('api_key_env', '')
            api_key = os.environ.get(api_key_env, '') if api_key_env else ''
        if provider != 'ollama' and not api_key:
            return None
        prompt = f"What is the English or alternative international title of the song '{track_name}' by '{artist_name}'? Return ONLY the title, nothing else. If unknown, return UNKNOWN."

        try:
            if provider == 'ollama':
                base_url = ai_config.get('ollama_base_url', 'http://localhost:11434')
                resp = requests.post(f"{base_url}/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=30)
                alt_name = resp.json().get('response', '').strip()
            elif provider == 'anthropic':
                resp = requests.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": model, "max_tokens": 50, "messages": [{"role": "user", "content": prompt}]}, timeout=30)
                alt_name = resp.json().get('content', [{}])[0].get('text', '').strip()
            else:  # openai-compatible (openai, deepseek, etc.)
                base_url = ai_config.get('base_url', 'https://api.openai.com')
                resp = requests.post(f"{base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 50}, timeout=30)
                alt_name = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        except Exception as e:
            print(f"  [AI fallback error] {e}")
            return None

        if resp.status_code != 200:
            return None
        if not alt_name or alt_name.upper() == 'UNKNOWN' or alt_name == track_name:
            return None

        # search Tidal with the AI-suggested name
        query = simple(alt_name) + ' ' + simple(artist_name)
        for track in tidal_session.search(query, models=[tidalapi.media.Track])['tracks']:
            if track.available and duration_match(track, spotify_track) and artist_match(track, spotify_track):
                print(f"  [AI match] '{track_name}' -> '{alt_name}' by {artist_name}")
                failure_cache.remove_match_failure(spotify_track['id'])
                return track
        return None

    # 1. Try ISRC lookup first (language-agnostic, most accurate)
    await rate_limiter.acquire()
    isrc_result = await asyncio.to_thread(_search_by_isrc)
    if isrc_result:
        return isrc_result

    # 2. Try album-based search
    await rate_limiter.acquire()
    album_search = await asyncio.to_thread( _search_for_track_in_album )
    if album_search:
        return album_search

    # 3. Try standalone track search
    await rate_limiter.acquire()
    track_search = await asyncio.to_thread( _search_for_standalone_track )
    if track_search:
        return track_search

    # 4. Try artist album browsing (cross-language fallback)
    await rate_limiter.acquire()
    artist_album_result = await asyncio.to_thread(_search_by_artist_albums)
    if artist_album_result:
        return artist_album_result

    # 5. Try AI fallback (optional, user-configured)
    if config and config.get('ai_fallback', {}).get('enabled'):
        await rate_limiter.acquire()
        ai_result = await asyncio.to_thread(_search_with_ai)
        if ai_result:
            return ai_result

    # if none of the search modes succeeded then store the track id to the failure cache
    failure_cache.cache_match_failure(spotify_track['id'])

async def repeat_on_request_error(function, *args, remaining=5, **kwargs):
    # utility to repeat calling the function up to 5 times if an exception is thrown
    try:
        return await function(*args, **kwargs)
    except (tidalapi.exceptions.TooManyRequests, requests.exceptions.RequestException, spotipy.exceptions.SpotifyException) as e:
        # don't retry permanent Spotify errors (playlist deleted, private, or no access)
        if isinstance(e, spotipy.exceptions.SpotifyException) and e.http_status in (403, 404):
            raise
        if remaining:
            print(f"{str(e)} occurred, retrying {remaining} times")
        else:
            print(f"{str(e)} could not be recovered")

        if isinstance(e, requests.exceptions.RequestException) and not e.response is None:
            print(f"Response message: {e.response.text}")
            print(f"Response headers: {e.response.headers}")

        if not remaining:
            print("Aborting sync")
            print(f"The following arguments were provided:\n\n {str(args)}")
            print(traceback.format_exc())
            sys.exit(1)
        sleep_schedule = {5: 1, 4:10, 3:60, 2:5*60, 1:10*60} # sleep variable length of time depending on retry number
        time.sleep(sleep_schedule.get(remaining, 1))
        return await repeat_on_request_error(function, *args, remaining=remaining-1, **kwargs)


async def _fetch_all_from_spotify_in_chunks(fetch_function: Callable) -> List[dict]:
    output = []
    results = fetch_function(0)
    for item in results.get("items", []):
        track = item.get("track") or item.get("item")
        if track:
            output.append(track)

    # Get all the remaining tracks in parallel
    if results['next']:
        offsets = [results['limit'] * n for n in range(1, math.ceil(results['total'] / results['limit']))]
        extra_results = await atqdm.gather(
            *[asyncio.to_thread(fetch_function, offset) for offset in offsets],
            desc="Fetching additional data chunks"
        )
        for extra_result in extra_results:
            for item in extra_result.get("items", []):
                track = item.get("track") or item.get("item")
                if track:
                    output.append(track)

    return output


async def get_tracks_from_spotify_playlist(spotify_session: spotipy.Spotify, spotify_playlist):
    def _get_tracks_from_spotify_playlist(offset: int, playlist_id: str):
        return spotify_session.playlist_tracks(playlist_id=playlist_id, offset=offset)

    print(f"Loading tracks from Spotify playlist '{spotify_playlist['name']}'")
    items = await repeat_on_request_error( _fetch_all_from_spotify_in_chunks, lambda offset: _get_tracks_from_spotify_playlist(offset=offset, playlist_id=spotify_playlist["id"]))
    track_filter = lambda item: item.get('type', 'track') == 'track' # type may be 'episode' also
    sanity_filter = lambda item: ('album' in item
                                  and 'name' in item['album']
                                  and 'artists' in item['album']
                                  and len(item['album']['artists']) > 0
                                  and item['album']['artists'][0]['name'] is not None)
    return list(filter(sanity_filter, filter(track_filter, items)))

def populate_track_match_cache(spotify_tracks_: Sequence[t_spotify.SpotifyTrack], tidal_tracks_: Sequence[tidalapi.Track]):
    """ Populate the track match cache with all the existing tracks in Tidal playlist corresponding to Spotify playlist """
    def _populate_one_track_from_spotify(spotify_track: t_spotify.SpotifyTrack):
        for idx, tidal_track in list(enumerate(tidal_tracks)):
            if tidal_track.available and match(tidal_track, spotify_track):
                track_match_cache.insert((spotify_track['id'], tidal_track.id))
                tidal_tracks.pop(idx)
                return

    def _populate_one_track_from_tidal(tidal_track: tidalapi.Track):
        for idx, spotify_track in list(enumerate(spotify_tracks)):
            if tidal_track.available and match(tidal_track, spotify_track):
                track_match_cache.insert((spotify_track['id'], tidal_track.id))
                spotify_tracks.pop(idx)
                return

    # make a copy of the tracks to avoid modifying original arrays
    spotify_tracks = [t for t in spotify_tracks_]
    tidal_tracks = [t for t in tidal_tracks_]

    # first populate from the tidal tracks
    for track in tidal_tracks:
        _populate_one_track_from_tidal(track)
    # then populate from the subset of Spotify tracks that didn't match (to account for many-to-one style mappings)
    for track in spotify_tracks:
        _populate_one_track_from_spotify(track)

def get_new_spotify_tracks(spotify_tracks: Sequence[t_spotify.SpotifyTrack]) -> List[t_spotify.SpotifyTrack]:
    ''' Extracts only the tracks that have not already been seen in our Tidal caches '''
    results = []
    for spotify_track in spotify_tracks:
        if not spotify_track['id']: continue
        if not track_match_cache.get(spotify_track['id']) and not failure_cache.has_match_failure(spotify_track['id']):
            results.append(spotify_track)
    return results

def get_tracks_for_new_tidal_playlist(spotify_tracks: Sequence[t_spotify.SpotifyTrack]) -> Sequence[int]:
    ''' gets list of corresponding tidal track ids for each spotify track, ignoring duplicates '''
    output = []
    seen_tracks = set()

    for spotify_track in spotify_tracks:
        if not spotify_track['id']: continue
        tidal_id = track_match_cache.get(spotify_track['id'])
        if tidal_id:
            if tidal_id in seen_tracks:
                track_name = spotify_track['name']
                artist_names = ', '.join([artist.get('name') or 'Unknown Artist' for artist in spotify_track.get('artists', [])])
                print(f'Duplicate found: Track "{track_name}" by {artist_names} will be ignored') 
            else:
                output.append(tidal_id)
                seen_tracks.add(tidal_id)
    return output

async def search_new_tracks_on_tidal(tidal_session: tidalapi.Session, spotify_tracks: Sequence[t_spotify.SpotifyTrack], playlist_name: str, config: dict):
    """ Generic function for searching for each item in a list of Spotify tracks which have not already been seen and adding them to the cache """
    async def _run_rate_limiter(semaphore):
        ''' Leaky bucket algorithm for rate limiting. Periodically releases items from semaphore at rate_limit'''
        _sleep_time = config.get('max_concurrency', 10)/config.get('rate_limit', 10)/4 # aim to sleep approx time to drain 1/4 of 'bucket'
        t0 = datetime.datetime.now()
        while True:
            await asyncio.sleep(_sleep_time)
            t = datetime.datetime.now()
            dt = (t - t0).total_seconds()
            new_items = round(config.get('rate_limit', 10)*dt)
            t0 = t
            [semaphore.release() for i in range(new_items)] # leak new_items from the 'bucket'

    # Extract the new tracks that do not already exist in the old tidal tracklist
    tracks_to_search = get_new_spotify_tracks(spotify_tracks)
    if not tracks_to_search:
        return

    # Search for each of the tracks on Tidal concurrently
    task_description = "Searching Tidal for {}/{} tracks in Spotify playlist '{}'".format(len(tracks_to_search), len(spotify_tracks), playlist_name)
    semaphore = asyncio.Semaphore(config.get('max_concurrency', 10))
    rate_limiter_task = asyncio.create_task(_run_rate_limiter(semaphore))
    search_results = await atqdm.gather( *[ repeat_on_request_error(tidal_search, t, semaphore, tidal_session, config=config) for t in tracks_to_search ], desc=task_description )
    rate_limiter_task.cancel()

    # Add the search results to the cache
    song404 = []
    for idx, spotify_track in enumerate(tracks_to_search):
        if search_results[idx]:
            track_match_cache.insert( (spotify_track['id'], search_results[idx].id) )
        else:
            artist_names = ",".join([a.get('name') or "Unknown Artist" for a in spotify_track.get('artists', [])])
            song404.append(f"{spotify_track['id']}: {artist_names} - {spotify_track.get('name') or 'Unknown Track'}")
            color = ('\033[91m', '\033[0m')
            print(color[0] + "Could not find the track " + song404[-1] + color[1])
    file_name = "songs not found.txt"
    header = f"==========================\nPlaylist: {playlist_name}\n==========================\n"
    with open(file_name, "a", encoding="utf-8") as file:
        file.write(header)
        for song in song404:
            file.write(f"{song}\n")

            
async def sync_playlist(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, spotify_playlist, tidal_playlist: tidalapi.Playlist | None, config: dict):
    """ sync given playlist to tidal """
    # Get the tracks from both Spotify and Tidal, creating a new Tidal playlist if necessary
    spotify_tracks = await get_tracks_from_spotify_playlist(spotify_session, spotify_playlist)
    if len(spotify_tracks) == 0:
        return # nothing to do
    if tidal_playlist:
        old_tidal_tracks = await get_all_playlist_tracks(tidal_playlist)
    else:
        print(f"No playlist found on Tidal corresponding to Spotify playlist: '{spotify_playlist['name']}', creating new playlist")
        tidal_playlist =  tidal_session.user.create_playlist(spotify_playlist['name'], spotify_playlist['description'])
        old_tidal_tracks = []

    # Extract the new tracks from the playlist that we haven't already seen before
    populate_track_match_cache(spotify_tracks, old_tidal_tracks)
    await search_new_tracks_on_tidal(tidal_session, spotify_tracks, spotify_playlist['name'], config)
    new_tidal_track_ids = get_tracks_for_new_tidal_playlist(spotify_tracks)

    # Update the Tidal playlist if there are changes
    old_tidal_track_ids = [t.id for t in old_tidal_tracks]
    if new_tidal_track_ids == old_tidal_track_ids:
        print("No changes to write to Tidal playlist")
    elif new_tidal_track_ids[:len(old_tidal_track_ids)] == old_tidal_track_ids:
        # Append new tracks to the existing playlist if possible
        add_multiple_tracks_to_playlist(tidal_playlist, new_tidal_track_ids[len(old_tidal_track_ids):])
    else:
        # Erase old playlist and add new tracks from scratch if any reordering occured
        clear_tidal_playlist(tidal_playlist)
        add_multiple_tracks_to_playlist(tidal_playlist, new_tidal_track_ids)

async def sync_favorites(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, config: dict):
    """ sync user favorites to tidal """
    async def get_tracks_from_spotify_favorites() -> List[dict]:
        _get_favorite_tracks = lambda offset: spotify_session.current_user_saved_tracks(offset=offset)    
        tracks = await repeat_on_request_error( _fetch_all_from_spotify_in_chunks, _get_favorite_tracks)
        tracks.reverse()
        return tracks

    def get_new_tidal_favorites() -> List[int]:
        existing_favorite_ids = set([track.id for track in old_tidal_tracks])
        new_ids = []
        for spotify_track in spotify_tracks:
            match_id = track_match_cache.get(spotify_track['id'])
            if match_id and not match_id in existing_favorite_ids:
                new_ids.append(match_id)
        return new_ids

    print("Loading favorite tracks from Spotify")
    spotify_tracks = await get_tracks_from_spotify_favorites()
    print("Loading existing favorite tracks from Tidal")
    old_tidal_tracks = await get_all_favorites(tidal_session.user.favorites, order='DATE')
    populate_track_match_cache(spotify_tracks, old_tidal_tracks)
    await search_new_tracks_on_tidal(tidal_session, spotify_tracks, "Favorites", config)
    new_tidal_favorite_ids = get_new_tidal_favorites()
    if new_tidal_favorite_ids:
        for tidal_id in tqdm(new_tidal_favorite_ids, desc="Adding new tracks to Tidal favorites"):
            tidal_session.user.favorites.add_track(tidal_id)
    else:
        print("No new tracks to add to Tidal favorites")

def sync_playlists_wrapper(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, playlists, config: dict):
  for spotify_playlist, tidal_playlist in playlists:
    # sync the spotify playlist to tidal
    try:
      asyncio.run(sync_playlist(spotify_session, tidal_session, spotify_playlist, tidal_playlist, config) )
    except spotipy.exceptions.SpotifyException as e:
      # skip playlists we can't access (deleted, private, or region-restricted)
      if e.http_status in (403, 404):
        name = spotify_playlist.get('name') if isinstance(spotify_playlist, dict) else getattr(spotify_playlist, 'name', '?')
        pid = spotify_playlist.get('id') if isinstance(spotify_playlist, dict) else getattr(spotify_playlist, 'id', '?')
        print(f"Skipping playlist '{name}' ({pid}): Spotify returned {e.http_status} — playlist inaccessible")
        continue
      raise

def sync_favorites_wrapper(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, config):
    asyncio.run(main=sync_favorites(spotify_session=spotify_session, tidal_session=tidal_session, config=config))

def get_tidal_playlists_wrapper(tidal_session: tidalapi.Session) -> Mapping[str, tidalapi.Playlist]:
    tidal_playlists = asyncio.run(get_all_playlists(tidal_session.user))
    return {playlist.name: playlist for playlist in tidal_playlists}

def pick_tidal_playlist_for_spotify_playlist(spotify_playlist, tidal_playlists: Mapping[str, tidalapi.Playlist]):
    if spotify_playlist['name'] in tidal_playlists:
      # if there's an existing tidal playlist with the name of the current playlist then use that
      tidal_playlist = tidal_playlists[spotify_playlist['name']]
      return (spotify_playlist, tidal_playlist)
    else:
      return (spotify_playlist, None)

def get_user_playlist_mappings(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, config):
    results = []
    spotify_playlists = asyncio.run(get_playlists_from_spotify(spotify_session, config))
    tidal_playlists = get_tidal_playlists_wrapper(tidal_session)
    for spotify_playlist in spotify_playlists:
        results.append( pick_tidal_playlist_for_spotify_playlist(spotify_playlist, tidal_playlists) )
    return results

async def get_playlists_from_spotify(spotify_session: spotipy.Spotify, config):
    # get all the playlists from the Spotify account
    playlists = []
    print("Loading Spotify playlists")
    first_results = spotify_session.current_user_playlists()
    exclude_list = set([x.split(':')[-1] for x in config.get('excluded_playlists', [])])
    playlists.extend([p for p in first_results['items']])
    user_id = spotify_session.current_user()['id']

    # get all the remaining playlists in parallel
    if first_results['next']:
        offsets = [ first_results['limit'] * n for n in range(1, math.ceil(first_results['total']/first_results['limit'])) ]
        extra_results = await atqdm.gather( *[asyncio.to_thread(spotify_session.current_user_playlists, offset=offset) for offset in offsets ] )
        for extra_result in extra_results:
            playlists.extend([p for p in extra_result['items']])

    # filter out playlists that don't belong to us (unless sync_followed_playlists is on) or are on the exclude list
    sync_followed = config.get('sync_followed_playlists', False)
    owner_filter = (lambda p: p) if sync_followed else (lambda p: p and p['owner']['id'] == user_id)
    exclude_filter = lambda p: not p['id'] in exclude_list
    return list(filter( exclude_filter, filter( owner_filter, playlists )))

def get_playlists_from_config(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, config):
    # get the list of playlist sync mappings from the configuration file
    def get_playlist_ids(config):
        return [(item['spotify_id'], item['tidal_id']) for item in config['sync_playlists']]
    output = []
    for spotify_id, tidal_id in get_playlist_ids(config=config):
        try:
            spotify_playlist = spotify_session.playlist(playlist_id=spotify_id)
        except spotipy.SpotifyException as e:
            print(f"Error getting Spotify playlist {spotify_id}")
            raise e
        try:
            tidal_playlist = tidal_session.playlist(playlist_id=tidal_id)
        except Exception as e:
            print(f"Error getting Tidal playlist {tidal_id}")
            raise e
        output.append((spotify_playlist, tidal_playlist))
    return output

