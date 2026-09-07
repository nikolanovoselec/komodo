# Hermes on openclaw.lan

Native, root-capable Hermes Agent deployment replacing the OpenClaw Docker stack.
The dashboard retains port `18789`; Signal Note to Self is primary and WhatsApp
self-chat is secondary. Google Chat and Home Assistant are intentionally absent.

This directory is public and contains no credentials. Runtime configuration,
OAuth state, messaging sessions, SSH private keys, and dashboard auth secrets are
stored in the private `nikolanovoselec/secrets` repository under
`hermes/openclaw-lan/` and installed with mode `0600`.

The OpenClaw containers must only be retired through Komodo's stack control
plane. Never stop, remove, or edit them directly on `openclaw.lan`.

Hermes uses a dedicated, persistent Chromium profile running as the unprivileged
`hermes-browser` user. CDP (`9222`) listens on loopback only. KasmVNC (`6080`)
serves the interactive browser on the server's LAN address so Nginx Proxy
Manager can publish it at `https://hermes.novoselec.ch/browser/` behind
Cloudflare Access.
The workstation also has a private SSH tunnel at
`http://127.0.0.1:6080/`.

```bash
ssh -L 6080:127.0.0.1:6080 root@openclaw.lan
```

There is no separate KasmVNC password; Cloudflare Access protects the public route.
Website sessions remain in `/var/lib/hermes-browser/profile`; never commit that
profile to this public repository.

For the safest manual login, first run
`hermes-browser-login-mode enter` on `openclaw.lan`. This stops Hermes and any
attached browser-automation daemons while leaving noVNC available. Log in and
complete MFA yourself, close the login form, then run
`hermes-browser-login-mode exit` to restore the dashboard and gateway.

The workstation bridge also installs a native Hyprland fallback using `grim`,
`wtype`, and `ydotool`. Hermes loads the `workstation-desktop` skill when CUA
Driver cannot capture a native Wayland window.
