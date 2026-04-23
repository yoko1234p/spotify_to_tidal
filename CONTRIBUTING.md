# Contributing to ToTidal

Thanks for your interest in improving ToTidal. This document covers how to file bugs, propose changes, and get a dev environment running.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ground rules

- **License:** ToTidal is AGPL-3.0-or-later. By opening a PR you agree your contribution is released under the same license.
- **Fork parity:** We routinely pull fixes from upstream [`spotify2tidal/spotify_to_tidal`](https://github.com/spotify2tidal/spotify_to_tidal). If your change fits upstream, please send it there first.
- **Commits:** Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). Commit messages may be in English or 繁體中文.
- **Scope:** One logical change per PR. Unrelated refactors belong in a separate PR.

## Reporting bugs

Open a [Bug Report](../../issues/new?template=bug.yml) issue. Include:

- `totidal --version`, OS + version, Python version
- The exact CLI command or GUI action that triggered the problem
- Redacted `config.yml` (strip `client_secret`, tokens, AI API keys)
- Full traceback from the terminal or `~/.totidal/diagnostic-bundle.zip` if the GUI generated one

## Proposing a feature

Open a [Feature Request](../../issues/new?template=feature.yml) first. Large features get discussed before implementation so you do not sink days into something we cannot merge.

## Dev setup

```bash
git clone https://github.com/MargeBurkszlp/totidal.git
cd totidal
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest tests/unit/ -q
```

## Running checks locally

```bash
.venv/bin/ruff check src tests
.venv/bin/pytest tests/unit/ -q
```

CI runs the same commands — green locally usually means green in CI.

## Pull requests

1. Open a branch from `main`. Branch names like `feat/<thing>` or `fix/<thing>` are preferred.
2. Keep the diff small. If the PR touches more than ~400 lines, split it.
3. Add or update a test for every bug you fix and every behaviour you add.
4. Update `CHANGELOG.md` under `## [Unreleased]`.
5. Open the PR against `main`. Reviewers will ask for changes in-line; push additional commits rather than force-pushing while review is in flight.

## Translations

Translation PRs are welcome. See [`docs/TRANSLATING.md`](docs/TRANSLATING.md) (added in Phase 1b).
