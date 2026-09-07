#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_dir/versions.env"

test "$(id -u)" -eq 0 || { echo "run as root" >&2; exit 1; }
test -f /root/.hermes/config.yaml || { echo "missing /root/.hermes/config.yaml" >&2; exit 1; }
test -f /root/.hermes/.env || { echo "missing /root/.hermes/.env" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git openssh-client build-essential python3 python3-venv openjdk-21-jre-headless

install -d -m 0700 /root/.hermes /root/.ssh
install -d -m 0755 /srv/hermes/workspaces /usr/local/lib

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

curl -fsSL \
  "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz" \
  -o "$tmp_dir/signal-cli.tar.gz"
tar -xzf "$tmp_dir/signal-cli.tar.gz" -C /opt
ln -sfn "/opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli" /usr/local/bin/signal-cli

install -m 0755 "$repo_dir/scripts/hermes-workstation-mcp" /usr/local/bin/hermes-workstation-mcp
install -m 0644 "$repo_dir/systemd/hermes-dashboard.service" /etc/systemd/system/hermes-dashboard.service
install -m 0644 "$repo_dir/systemd/hermes-gateway.service" /etc/systemd/system/hermes-gateway.service
install -m 0644 "$repo_dir/systemd/signal-cli.service" /etc/systemd/system/signal-cli.service

systemctl daemon-reload
echo "Hermes installed. Authentication and messaging linkage must be completed before enabling services."
