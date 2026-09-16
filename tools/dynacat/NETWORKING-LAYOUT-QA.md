# Networking layout acceptance

Scope owner: networking template and networking.css only, plus frontend Compose revision and QA. Collector code/revision, other pages, disclosure JS and graph generation are unchanged.

- [x] Actual UDM SE gateway gets a prominent node-style widget.
- [x] Remaining live devices grouped into Switches, Access points, Internet backup.
- [x] Group classification uses provider kind and exact U-LTE-Pro model, never friendly names. Unknown kinds remain visible outside the three groups.
- [x] Each device retains CPU, memory, uplink RX/TX, identity, status, port/client/uptime values.
- [x] Compact workload-style shaded history preserves source paths and independently closed gap segments, scales, 30-minute window, sparse dots, unavailable/collecting states.
- [x] Existing clients/search, network/WiFi inventory, firewall/capabilities disclosures remain usable.
- [x] Same captured-production source compared through native panonim/dynacat:3.0.0 renderer at 1600 and 390 pixels in both themes, mobile emulation enabled.
- [x] Real rendered values and path/area strings checked against captured source; no aggregates or synthetic operational metrics.
- [x] Asset digest test passes; frontend revision only changes.

## Evidence

Local evidence is retained in `networking-layout-qa/` (not committed because it contains internal inventory). Includes timestamped production config/assets backup and hash manifest, baseline/candidate/live screenshots and JSON reports, RED/GREEN logs. All 22 tracked deployed config/asset files matched release baseline `0488fe8c`; generated runtime cache files are backed up but not tracked.

TDD: native candidate layout acceptance failed against unchanged production baseline (no gateway/grouping/areas/compactness), then passed after scoped implementation. Existing native synthetic contract QA additionally passes changed-fixture refresh/caret/disclosure restoration, null versus zero, sparse dots and unavailable source branches.

| Measurement | Baseline | Candidate |
|---|---:|---:|
| Desktop device card / compact row | 355.95 px | 88.34 px |
| Mobile device card / compact row | 351.95 px | 229.86 px |
| Desktop gateway | 355.95 px | 305.27 px, full-width prominent node |
| Mobile gateway | 351.95 px | 436.56 px |
| Compact chart height desktop / mobile | 44 / 44 px | 26 / 24 px |

Both themes match geometry. Gateway prominence comes from full-width geometry, larger current readings and 66px histories rather than increasing every desktop card height. Whole-section compactness is separately asserted; row reduction is not substituted for section reduction.

Commands (Python environment needs YAML and Playwright; local Docker required):

```sh
python tools/dynacat/qa_networking_layout.py baseline
python tools/dynacat/qa_networking_layout.py candidate
python tools/dynacat/qa_networking_layout.py live --url http://192.168.2.72:8080/networking
python tools/dynacat/qa_networking.py
python -m unittest discover -s tools/dynacat -p 'test_*.py'
python -m unittest discover -s tools/dynacat/adapter -p 'test_*.py'
NODE_PATH=/tmp/networking-node-qa/node_modules node --test tools/dynacat/assets/networking.test.cjs
```

Captured-real QA leaves its source immutable and checks public restoration events. Actual changed-data refresh uses the separately labeled synthetic contract harness. Native renderers block media playback. Deployment is tracked Git/Komodo only; SSH is read-only verification.
