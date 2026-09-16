# Networking query-chart frontend acceptance

## Scope
- [x] Entire Connected clients section removed.
- [x] Pi-hole full width below unchanged Infrastructure template.
- [x] Three counters retained; partial totals and unavailable remain distinct.
- [x] Both recent-domain lists removed; one combined shaded chart consumes backend paths verbatim.
- [x] Shared 600×140 viewBox / count scale, UTC endpoint labels, interval label derived from `interval_seconds`.
- [x] Honest permitted legend (total minus blocked, not guaranteed successful resolutions).
- [x] Missing history shown unavailable; incomplete history warning independent of summary counters.
- [x] CSS digest matches production asset wiring.
- [x] Native 1600/390 dark/light capture, touch-emulated phone swipe and position retained across native refresh.
- [ ] Captured-real populated query chart (current deployed API does not yet expose query_history).
- [ ] Release and live post-release verification (release owner only).

## Evidence
Native TDD observed:
1. Client/full-width test RED: two removed client UI elements still present. Removed client section and changed one-column lower grid. GREEN: 2 tests passed.
2. Combined chart test RED: `.nw-query-chart svg` absent. Replaced lists, added chart/CSS using backend paths. GREEN: 3 tests passed.
3. Additional regression coverage for existing missing/partial/unavailable semantics: full frontend suite 4 passed.
4. Existing JS suite: 1 passed (`NODE_PATH=/tmp/networking-node-qa/node_modules node --test tools/dynacat/assets/networking.test.cjs`).

`networking-query-qa/candidate-{dark,light}-{1600,390}-{page,pihole}.png` are actual captured-real native screenshots. Source fetched read-only from collector via workstation SSH; removed clients and recent domain arrays before stdout/export. Pi-hole counters: 556366 / 239592 / 6752986. The API currently lacks query_history, so these screenshots honestly show history unavailable. Synthetic gap-path fixtures are confined to native tests, not presented as captured-real data. Native report: `networking-query-qa/candidate-report.json`, all four layouts without overflow or JS errors. Infrastructure paths compared verbatim against captured source.

## Re-run and release handoff
Use a new actual capture that includes the candidate backend's query_history. Do not fabricate a history object or export recent domain records.

```sh
NETWORK_QA_SOURCE=/absolute/sanitized/network-current.json \
 /srv/hermes/workspaces/dynacat-qa-venv/bin/python -m pytest tools/dynacat/test_networking_lower.py -q
NETWORK_QA_SOURCE=/absolute/sanitized/network-current.json \
 /srv/hermes/workspaces/dynacat-qa-venv/bin/python tools/dynacat/qa_networking_lower.py
```

The second command creates an isolated native renderer (production head and assets intact), compares each line and shaded area exactly to the captured backend response, checks both themes and mobile touch refresh, then removes local QA containers. It never deploys.

After release owner pushes and verifies deployment, point `--url` at the read-only forwarded deployed dashboard, e.g.:

```sh
NETWORK_QA_SOURCE=/absolute/sanitized/network-current.json \
 /srv/hermes/workspaces/dynacat-qa-venv/bin/python tools/dynacat/qa_networking_lower.py \
 --url http://127.0.0.1:FORWARDED_PORT/networking
```

Live screenshots/report use `live-*`; rapidly changing paths should be verified against the exact widget response separately. No commit, push, backend edit or live mutation was performed by frontend owner.
