# Security Policy

## Supported versions

Only the latest `1.x` release gets security fixes. If you are on an older release, upgrade first.

| Version | Supported |
|---|---|
| 1.0.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.**

Email `security@totidal.dev` with:

- A description of the issue and its impact.
- Steps to reproduce (PoC welcome).
- The ToTidal version, OS, and Python version.

We aim to:

- Acknowledge the report within **72 hours**.
- Ship a fix or public advisory within **30 days** for P0 / P1 issues.

If you would like your report public-attributed after the fix ships, say so — otherwise we will keep it anonymous.

## Scope

In scope:

- The `totidal` CLI, the `totidal_backend` Python package, and the Tauri desktop app (Phase 1+).
- Local IPC between the desktop app and its Python sidecar.
- Handling of Spotify / Tidal OAuth tokens, AI API keys, and other credentials on disk or in memory.

Out of scope:

- Vulnerabilities in upstream Spotify, Tidal, or AI provider APIs — please report those to the respective vendors.
- Attacks requiring prior root/admin access to the user's machine.
