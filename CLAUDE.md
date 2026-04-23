# ToTidal Project Rules

## Secrets handling

**Never read `config.yml`.** It contains real Spotify client secrets and AI API keys that trigger content-filter blocks when reflected into long outputs. Use `example_config.yml` as the reference for config schema instead.

If you need to verify a config shape, read `example_config.yml`. If you need to modify user-facing config documentation, edit `example_config.yml`.

Never paste values from `config.yml` into chat, plan docs, commit messages, or any other output.
