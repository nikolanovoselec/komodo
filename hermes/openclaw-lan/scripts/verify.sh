#!/usr/bin/env bash
set -euo pipefail

fail=0
check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    fail=1
  fi
}

check "Hermes executable" /usr/local/bin/hermes --version
check "Hermes pinned checkout" test "$(git -C /usr/local/lib/hermes-agent rev-parse HEAD)" = "29112bef099274229cadff79cdff7bf7b99c4b77"
check "signal-cli executable" /usr/local/bin/signal-cli --version
check "workstation SSH" ssh -T -i /root/.ssh/hermes-workstation -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=5 nikolanovoselec@192.168.1.109 true
check "workstation Codex" ssh -T -i /root/.ssh/hermes-workstation -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=5 nikolanovoselec@192.168.1.109 /usr/local/bin/hermes-codex-mcp --version
check "dashboard" curl -fsS http://127.0.0.1:18789/
check "gateway service" systemctl is-active hermes-gateway.service

exit "$fail"
