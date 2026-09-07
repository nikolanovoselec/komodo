#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$repo_dir/../versions.env"
test "$(id -u)" -eq 0 || { echo "run as root" >&2; exit 1; }
test -n "${HERMES_AUTHORIZED_KEY:-}" || { echo "set HERMES_AUTHORIZED_KEY" >&2; exit 1; }

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
printf 'nikolanovoselec ALL=(ALL:ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/90-hermes-agent
chmod 0440 /etc/sudoers.d/90-hermes-agent
visudo -cf /etc/sudoers.d/90-hermes-agent
systemctl enable --now sshd.service

runuser -u nikolanovoselec -- /home/nikolanovoselec/.local/bin/cua-driver --version
echo "Workstation bridge installed."
