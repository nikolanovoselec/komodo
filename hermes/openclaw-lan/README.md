# Hermes on openclaw.lan

Native, root-capable Hermes Agent deployment replacing the OpenClaw Docker stack.
The dashboard retains port `18789`; Signal Note to Self is primary and WhatsApp
self-chat is secondary. Google Chat and Home Assistant are intentionally absent.

This directory is public and contains no credentials. Runtime configuration,
OAuth state, messaging sessions, SSH private keys, and dashboard credentials are
stored in the private `nikolanovoselec/secrets` repository under
`hermes/openclaw-lan/` and installed with mode `0600`.

The OpenClaw containers must only be retired through Komodo's stack control
plane. Never stop, remove, or edit them directly on `openclaw.lan`.

Hermes uses a dedicated, persistent Chromium profile running as the unprivileged
`hermes-browser` user. CDP (`9222`), VNC (`5900`), and noVNC (`6080`) listen on
loopback only. To log into websites without giving credentials to the agent,
forward noVNC over SSH and open `http://127.0.0.1:6080/vnc.html` locally:

```bash
ssh -L 6080:127.0.0.1:6080 root@openclaw.lan
```

Use `HERMES_BROWSER_VNC_PASSWORD` from the private Hermes secrets. Website
sessions remain in `/var/lib/hermes-browser/profile`; never commit that profile
to this public repository.
