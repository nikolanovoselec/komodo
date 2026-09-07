#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$repo_dir/../versions.env"
test "$(id -u)" -eq 0 || { echo "run as root" >&2; exit 1; }
test -n "${HERMES_AUTHORIZED_KEY:-}" || { echo "set HERMES_AUTHORIZED_KEY" >&2; exit 1; }
test -f "${HERMES_TUNNEL_KEY_FILE:-}" || { echo "set HERMES_TUNNEL_KEY_FILE" >&2; exit 1; }

pacman -S --needed --noconfirm openssh

current_cua="$(runuser -u nikolanovoselec -- /home/nikolanovoselec/.local/bin/cua-driver --version 2>/dev/null | awk '{print $2}' || true)"
if [[ "$current_cua" != "$CUA_DRIVER_VERSION" ]]; then
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf -- "$tmp_dir"' EXIT
  curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.sh -o "$tmp_dir/cua-install.sh"
  runuser -u nikolanovoselec -- env \
    HOME=/home/nikolanovoselec \
    CUA_DRIVER_VERSION="$CUA_DRIVER_VERSION" \
    CUA_DRIVER_NO_MODIFY_PATH=1 \
    bash "$tmp_dir/cua-install.sh" \
      --bin-dir /home/nikolanovoselec/.local/bin \
      --no-modify-path
fi
runuser -u nikolanovoselec -- env HOME=/home/nikolanovoselec /home/nikolanovoselec/.local/bin/cua-driver telemetry disable

install -d -o nikolanovoselec -g nikolanovoselec -m 0700 /home/nikolanovoselec/.ssh
touch /home/nikolanovoselec/.ssh/authorized_keys
chown nikolanovoselec:nikolanovoselec /home/nikolanovoselec/.ssh/authorized_keys
chmod 0600 /home/nikolanovoselec/.ssh/authorized_keys
grep -qxF "$HERMES_AUTHORIZED_KEY" /home/nikolanovoselec/.ssh/authorized_keys || printf '%s\n' "$HERMES_AUTHORIZED_KEY" >> /home/nikolanovoselec/.ssh/authorized_keys

install -m 0755 "$repo_dir/hermes-codex-mcp" /usr/local/bin/hermes-codex-mcp
install -m 0755 "$repo_dir/hermes-cua-mcp" /usr/local/bin/hermes-cua-mcp
install -o nikolanovoselec -g nikolanovoselec -m 0600 "$HERMES_TUNNEL_KEY_FILE" /home/nikolanovoselec/.ssh/hermes-openclaw-tunnel
install -m 0644 "$repo_dir/hermes-openclaw-tunnel.service" /etc/systemd/system/hermes-openclaw-tunnel.service
printf 'nikolanovoselec ALL=(ALL:ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/90-hermes-agent
chmod 0440 /etc/sudoers.d/90-hermes-agent
visudo -cf /etc/sudoers.d/90-hermes-agent
systemctl enable --now sshd.service
systemctl daemon-reload
systemctl enable --now hermes-openclaw-tunnel.service
if command -v ufw >/dev/null 2>&1; then
  ufw allow from 192.168.3.203 to any port 22 proto tcp comment 'Hermes openclaw workstation bridge'
fi

runuser -u nikolanovoselec -- /home/nikolanovoselec/.local/bin/cua-driver --version
echo "Workstation bridge installed."
