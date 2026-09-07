#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_dir/versions.env"

test "$(id -u)" -eq 0 || { echo "run as root" >&2; exit 1; }
test -f /root/.hermes/config.yaml || { echo "missing /root/.hermes/config.yaml" >&2; exit 1; }
test -f /root/.hermes/.env || { echo "missing /root/.hermes/.env" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git gh openssh-client build-essential python3 python3-venv openjdk-21-jre-headless chromium

install -d -m 0700 /root/.hermes /root/.ssh
install -d -m 0755 /srv/hermes/workspaces /usr/local/lib

if ! id -u hermes-browser >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/hermes-browser --shell /usr/sbin/nologin hermes-browser
fi
install -d -o hermes-browser -g hermes-browser -m 0700 /var/lib/hermes-browser/profile

if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  if [[ ! -e /swapfile ]]; then
    fallocate -l 8G /swapfile
    chmod 0600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
fi
grep -qE '^/swapfile[[:space:]]' /etc/fstab || printf '/swapfile none swap sw 0 0\n' >> /etc/fstab

tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT

curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o "$tmp_dir/hermes-install.sh"
bash "$tmp_dir/hermes-install.sh" \
  --skip-setup \
  --branch "$HERMES_TAG" \
  --commit "$HERMES_COMMIT" \
  --force-commit \
  --dir /usr/local/lib/hermes-agent \
  --hermes-home /root/.hermes
# The pinned tag checkout is intentionally detached, but Hermes' built-in
# updater follows origin/main. Ensure the branch ref remains fetchable.
git -C /usr/local/lib/hermes-agent config \
  remote.origin.fetch '+refs/heads/main:refs/remotes/origin/main'
git -C /usr/local/lib/hermes-agent fetch --prune origin main
ln -sfn /root/.local/bin/hermes /usr/local/bin/hermes
/root/.hermes/bin/uv pip install --quiet --upgrade \
  --python /usr/local/lib/hermes-agent/venv/bin/python \
  ddgs

kasmvnc_package="$tmp_dir/kasmvncserver_trixie_${KASMVNC_VERSION}_amd64.deb"
curl -fsSL \
  "https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_trixie_${KASMVNC_VERSION}_amd64.deb" \
  -o "$kasmvnc_package"
printf '%s  %s\n' "$KASMVNC_SHA256" "$kasmvnc_package" | sha256sum -c -
apt-get install -y "$kasmvnc_package"

curl -fsSL \
  "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz" \
  -o "$tmp_dir/signal-cli.tar.gz"
tar -xzf "$tmp_dir/signal-cli.tar.gz" -C /opt
ln -sfn /opt/signal-cli /usr/local/bin/signal-cli

install -m 0755 "$repo_dir/scripts/hermes-workstation-mcp" /usr/local/bin/hermes-workstation-mcp
install -m 0755 "$repo_dir/scripts/hermes-workstation-desktop" /usr/local/bin/hermes-workstation-desktop
install -m 0755 "$repo_dir/scripts/hermes-network-ssh" /usr/local/bin/hermes-network-ssh
install -m 0755 "$repo_dir/scripts/hermes-browser-login-mode" /usr/local/bin/hermes-browser-login-mode
install -d -m 0755 /root/.hermes/skills/workstation-desktop
install -m 0644 "$repo_dir/skills/workstation-desktop/SKILL.md" /root/.hermes/skills/workstation-desktop/SKILL.md
install -d -m 0755 /root/.hermes/skills/network-ssh
install -m 0644 "$repo_dir/skills/network-ssh/SKILL.md" /root/.hermes/skills/network-ssh/SKILL.md
install -m 0644 "$repo_dir/systemd/hermes-dashboard.service" /etc/systemd/system/hermes-dashboard.service
install -m 0644 "$repo_dir/systemd/hermes-gateway.service" /etc/systemd/system/hermes-gateway.service
install -m 0644 "$repo_dir/systemd/hermes-browser-display.service" /etc/systemd/system/hermes-browser-display.service
install -m 0644 "$repo_dir/systemd/hermes-browser.service" /etc/systemd/system/hermes-browser.service
install -m 0644 "$repo_dir/systemd/signal-cli.service" /etc/systemd/system/signal-cli.service

systemctl disable --now hermes-browser-novnc.service 2>/dev/null || true
rm -f /etc/systemd/system/hermes-browser-novnc.service

systemctl daemon-reload
echo "Hermes installed. Authentication and messaging linkage must be completed before enabling services."
