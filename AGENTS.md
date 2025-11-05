# Repository Guidelines

## Project Structure & Module Organization
The repo is arranged by server cluster. Directories such as `dns_ntp/`, `media_servers/`, `middleware/`, `minecraft/`, `storage/`, `tools/`, and `ai_llm/` house service-specific `compose.yaml` definitions. Every stack is mirrored under `komodo_core/`, where `main.toml` registers servers, stacks, procedures, actions, and resource sync rules. Keep new stacks under the matching server directory and reference them from `komodo_core/main.toml` so Komodo can deploy them consistently.

## Build, Test, and Development Commands
Use `docker compose -f <dir>/<service>/compose.yaml config` to lint a compose file before pushing (for example, `docker compose -f tools/zipline/compose.yaml config`). Run `docker compose -f <dir>/<service>/compose.yaml pull` to confirm image availability. After editing `main.toml`, validate syntax with `python -m tomllib komodo_core/main.toml` (Python ≥3.11) or `toml-lint`. Always review `git diff` before committing to ensure generated secrets or local paths are not staged.

## Coding Style & Naming Conventions
Keep YAML indentation at two spaces and align lists under parent keys. Container and stack names follow `<server>_<service>` (see `dns_ntp/backrest/compose.yaml`). Environment placeholders use double brackets (`[[SECRET_NAME]]`) so Komodo resource sync can inject values; do not switch to `${VAR}` unless the value is provided locally. Favor lowercase directory names with underscores, matching the server identifiers inside `komodo_core/main.toml`.

## Testing Guidelines
There is no dedicated test suite; validation focuses on configuration hygiene. Execute the compose `config` check and, when possible, run `docker compose -f ... up --detach` in a sandbox to confirm startup. For Komodo automation, trigger `Deploy Stacks If Changed` after staging updates and monitor the terminal output to ensure actions finish with exit code 0.

## Commit & Pull Request Guidelines
Adopt Conventional Commits (`chore: pin postgres 16 for zipline`) for atomic changes. Group unrelated updates into separate commits so Renovate and auto-update tooling stay effective. Pull requests should summarize the service touched, outline operational impact (downtime, new ports), and link issues or change tickets when available. Include verification notes (compose lint output, manual deploy results) and flag any secrets that must be rotated post-merge.

## Secrets & Access
Secrets live in the external `secrets` repo via resource sync; keep placeholders intact and document new keys in `SECRETS.md`. Never commit concrete credentials or LAN addresses beyond what already exists, and rotate webhook secrets if exposure is suspected.
