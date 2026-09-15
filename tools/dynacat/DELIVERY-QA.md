# Sonarr/Radarr delivery verification

Queue and recent-import cells activate their unchanged source URL across the full cell. IMDb remains a separate accessible action above the stretched link, with no nested anchors. Missing source URLs show `Source link unavailable`, not an invented link. Keyboard focus outlines the whole cell.

Visual hierarchy separates title/percentage, status, progress, remaining size and ETA. Empty ETA is explicitly unavailable. Source freshness, truncation and empty/error states remain intact. New rules use `mo-arr-delivery`, leaving qBittorrent, Plex sessions, radio and traffic unchanged.

## Synthetic active-queue QA

```sh
/srv/hermes/workspaces/dynacat-qa-venv/bin/python qa_delivery.py
```

Requires Docker, the local `media-compact-qa` network, `panonim/dynacat:3.0.0`, `python:3.13-slim`, Playwright and PyYAML. Only local containers `delivery-qa-source` and `delivery-qa-stage` are created; the candidate binds localhost port 18129. Production configuration is never rewritten by this script.

All fixture content is labelled **SYNTHETIC · NOT LIVE**. The browser suite checks 24 row/theme/viewport combinations at 360/390/1600px, with touch contexts and actual Catppuccin Latte/dark themes. It checks five-point hit targets, intercepted corner-click dispatch to exact URLs, independent IMDb actionability, Tab focus, missing URLs, progress, metadata, freshness and empty/error states. Links are not followed; no download or playback is initiated.

RED runs demonstrated missing full-cell hit targets and missing metadata hierarchy before implementation. Evidence is stored outside Git under `/srv/hermes/workspaces/delivery-qa-evidence/`.

## Structural redesign acceptance

The second pass separates the compact queue total from collapsed import history, removes routine API-age boilerplate, reserves accent color for active progress, and aligns import metadata without repeated green checkmarks. Default empty widgets measure about 216px versus 564px previously, using the same captured real data and native renderer. All 12 imports remain accessible in each disclosure. Source URLs, independent IMDb actions, error/empty/truncation states, real percentages, remaining sizes and ETA remain intact.

`qa_delivery_redesign.py` renders deployed baseline and candidate against the same captured ARR response. Evidence: `/srv/hermes/workspaces/delivery-redesign-evidence/`, with six desktop/mobile theme combinations, default and expanded screenshots, and geometry JSON. Expanded and collapsed state are asserted after both widgets actually render a changed local refresh fixture, then restore captured content. The fixture source is local and never changes operational downloads.

Secret-scanned deployed baseline: `/srv/hermes/workspaces/delivery-redesign-baseline/deployed.tar.gz` and `manifest.json`, revision `c554389b0849388ceee299081c63c6e48a91f5b1`; archive CSS hash matched live served CSS before edits. Baseline live screenshots: `/srv/hermes/workspaces/delivery-redesign-before/`. This is staged acceptance, not proof of deployment. Parent coordinates the shared release and must rerun live QA and stack health verification.

## Live read-only QA

```sh
/srv/hermes/workspaces/dynacat-qa-venv/bin/python qa_delivery_live.py \
  http://192.168.2.72:8080 /srv/hermes/workspaces/delivery-live-qa
```

The live suite records actual queue/import counts, verifies row hit targets and keyboard focus, intercepts clicks without navigating, and captures desktop/mobile light/dark evidence. Empty live queues do not count as active-download verification; use the explicitly labelled fixture suite for that state. The baseline source inspection found zero queued entries and 12 recent imports for each application; these counts are observations, not fixtures or guaranteed current totals.

`test_delivery_scope.py` guards isolation from qBittorrent. `test_mobile_repair.py` enforces asset-content version hashes. Deploy through Git/Komodo and verify production separately from staged success.

After testing, remove only the known local staging containers:

```sh
docker rm -f delivery-qa-stage delivery-qa-source
```
