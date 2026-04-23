# ToTidal

[![CI](https://github.com/MargeBurkszlp/totidal/actions/workflows/backend.yml/badge.svg)](https://github.com/MargeBurkszlp/totidal/actions/workflows/backend.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPLv3-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Sync your Spotify playlists and liked songs to Tidal. Cross-language track matching, graceful handling of unavailable playlists, and an optional AI fallback for tracks with transliterated names.

> **Fork notice:** ToTidal is a fork of [spotify2tidal/spotify_to_tidal](https://github.com/spotify2tidal/spotify_to_tidal). The upstream project is released under AGPL-3.0 and so is this fork — see [`NOTICE`](NOTICE) for attribution and [`LICENSE`](LICENSE) for the full license text.

## What's different from upstream

| Area | Upstream `spotify_to_tidal` | This fork (`ToTidal`) |
|---|---|---|
| Followed playlists | Owner-only | Optional: `sync_followed_playlists: true` |
| Inaccessible playlists | Abort the whole run | Log and skip, continue with the rest |
| Cross-language tracks | Exact search only | Artist-album browse + AI fallback |
| GUI | CLI only | CLI plus a cross-platform desktop app (Phase 1, in progress) |
| Python package name | `spotify_to_tidal` | `totidal_backend` (old name kept as a deprecation shim) |

## Install

```bash
git clone https://github.com/MargeBurkszlp/totidal.git
cd totidal
python3 -m pip install -e .
```

Requires Python 3.10 or newer.

## Set up

1. Copy `example_config.yml` to `config.yml`.
2. Register a Spotify app at <https://developer.spotify.com/dashboard> and paste the client ID, client secret, and your Spotify username into `config.yml`. Add `http://127.0.0.1:8888/callback` as a Redirect URI on the Spotify app page.
3. (Optional) Under `ai_fallback:` in `config.yml`, pick a provider (`openai`, `anthropic`, `deepseek`, `ollama`, or any OpenAI-compatible API) and paste a key — used only for tracks that the normal search can't resolve.

## Use

Sync everything (your playlists + liked songs):
```bash
totidal
```

Sync a single playlist by URI or ID:
```bash
totidal --uri 1ABCDEqsABCD6EaABCDa0a
```

Liked songs only:
```bash
totidal --sync-favorites
```

Retry tracks that previously failed (clears the failure cache):
```bash
totidal --retry-failed
```

See `example_config.yml` for all configuration options.

## Upgrading from `spotify_to_tidal`

The Python import `spotify_to_tidal` and the CLI name `spotify_to_tidal` both still work and emit a `DeprecationWarning`. Before the next minor release, update imports to `totidal_backend` and switch your shell muscle memory to `totidal`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). By contributing you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

To report a security vulnerability, see [`SECURITY.md`](SECURITY.md). Do not open a public issue.

## License

AGPL-3.0-or-later — see [`LICENSE`](LICENSE). If you run a modified version of this program as a network service, you must offer users the source of your modified version.
