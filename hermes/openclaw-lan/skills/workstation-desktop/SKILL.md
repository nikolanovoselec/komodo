---
name: workstation-desktop
description: See and control the user's Hyprland workstation through the private SSH bridge.
---

# Workstation desktop

Use this skill when the user asks you to inspect, operate, or assist with the
visible workstation desktop. The native Wayland fallback is
`/usr/local/bin/hermes-workstation-desktop`.

1. Capture the desktop to an allowed local path:

   `hermes-workstation-desktop screenshot /srv/hermes/workspaces/workstation-screen.png`

2. Use the vision tool to inspect that PNG. Its pixels are the action
   coordinates for the 7680x2160 desktop.
3. Act with one of:

   - `hermes-workstation-desktop move X Y`
   - `hermes-workstation-desktop click X Y`
   - `hermes-workstation-desktop type 'text'`
   - `hermes-workstation-desktop key Return`
   - `hermes-workstation-desktop hotkey ctrl l`
   - `hermes-workstation-desktop active-window`
   - `hermes-workstation-desktop clients`

4. Capture and inspect a fresh screenshot after every material action.

Prefer the `workstation_cua` MCP tools when they succeed. Use this fallback for
native Wayland windows or when CUA Driver reports an X11 capture error. Never
ask the user to paste passwords or one-time codes into chat. Pause while the
user enters credentials personally, then continue only after they say the login
is complete.
