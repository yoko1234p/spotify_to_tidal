# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet.

## [1.0.7] — 2026-04-23

### Added
- Forked from [spotify2tidal/spotify_to_tidal](https://github.com/spotify2tidal/spotify_to_tidal) and renamed to **ToTidal**.
- Python distribution renamed: `spotify_to_tidal` → `totidal-backend`.
- `totidal` CLI entry point. The legacy `spotify_to_tidal` entry point is kept as an alias.
- Config option `sync_followed_playlists` (default: `false`) to sync playlists you follow from other users.
- Graceful skip of Spotify 403/404 playlists (editorial/algorithmic/deleted) instead of aborting the whole sync.
- Cross-language track matching via artist-album browsing plus optional AI fallback (DeepSeek, OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint).
- Community infrastructure: `NOTICE`, `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue/PR templates, `dependabot.yml`, `ruff.toml`, and CI workflow skeletons.
- `scripts/bump-version.py` as the single source of truth for version bumps.

### Changed
- Minimum Python version raised to 3.10 (matches the upstream pin and drops EOL 3.9).

### Deprecated
- The `spotify_to_tidal` Python import path and `python -m spotify_to_tidal` invocation. Both still work and emit a `DeprecationWarning`; they will be removed no earlier than the release after 1.0.7.

[Unreleased]: https://github.com/yoko1234p/spotify_to_tidal/compare/v1.0.7...HEAD
[1.0.7]: https://github.com/yoko1234p/spotify_to_tidal/releases/tag/v1.0.7
