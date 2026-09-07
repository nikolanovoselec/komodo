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
