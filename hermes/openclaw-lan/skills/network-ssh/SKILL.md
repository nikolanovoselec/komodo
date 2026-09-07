---
name: network-ssh
description: Connect to the user's LAN devices through the workstation's 1Password SSH agent.
---

# Network SSH

Use this skill when the user asks to inspect or operate a device reachable from
their workstation over SSH. Run:

`/usr/local/bin/hermes-network-ssh user@host 'command'`

Use an explicit `user@host` target. For the user's infrastructure, `root@host`
is normally appropriate unless the user specifies another account. The bridge
uses the workstation's 1Password SSH agent, IPv4, public-key authentication,
and reusable SSH connections.

Start with read-only inspection before making changes. Operate only the hosts
the user names or clearly places in scope. Never ask the user to send private
keys, passwords, or one-time codes through chat. If 1Password requests approval
or is locked, ask the user to approve or unlock it on the workstation.
