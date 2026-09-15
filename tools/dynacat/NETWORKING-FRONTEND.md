# NETWORKING frontend integration

Native Dynacat 3.0.0 custom-api page, route `/networking`, after Hardware & Workloads. The page only requests the private adapter `/network-current` server-side. No UniFi credentials or direct UniFi browser requests.

## Integration owner checklist

- Wire `/assets/networking.css` and deferred `/assets/networking.js` into document.head with actual content hashes.
- Refresh document.head hash for modified `command-center.js`.
- Refresh gateway-injected `dashboard-navigation.js` import hash AND containing module URL. Route allowlist, mobile choices and `d n` chord are implemented; retain existing route lifecycle hook to avoid audio interruption.
- Backend contract supplied by parent: `state,error,site,summary,devices,clients,networks,wifi,wan,capabilities,partial`; null/missing readings display unavailable, not zero. Do not pass unsanitized upstream payloads or credentials.
- Histories use `history.cpu/ram/rx/tx` with `path`, `dots:[{x,y}]`, `samples`, `scale`, `state`, `window_seconds:1800`. Geometry must be 0..100 x 0..30, with path gaps intact. Rate values and scales are Mbps. Single-sample histories display collecting instead of an invented trend.
- Optional `firewall:{available,reason,rules:[{id,name,enabled,action,source,destination,protocol,port}]}` renders read-only under a disclosure. Source/destination/protocol/port must be safe scalar display strings, not objects. Missing fields explicitly unavailable; no rule mutation controls.
- Device names become links only when backend provides a verified URL. No guessed management links.
- Port counts and clients/uptime are supported. Per-port/radio/uplink details require a confirmed additional contract; not invented in this frontend.
- Live adapter data, full integrated routing/radio browser check, deployment and hash wiring are the parent's remaining integration steps.

## Verification

RED→GREEN captured for native page creation, native synthetic site/metrics render, SPA NETWORKING route, caret restoration, and optional firewall/sparse-sample support. Independent final reviewer passed.

```sh
/srv/hermes/workspaces/dynacat-qa-venv/bin/python -m unittest test_networking -v
NODE_PATH=/tmp/networking-node-qa/node_modules node --test assets/networking.test.cjs assets/dashboard-navigation.test.cjs assets/plex-radio.test.cjs
/srv/hermes/workspaces/dynacat-qa-venv/bin/python qa_networking.py
```

Native QA needs Docker, existing `media-compact-qa` network, `panonim/dynacat:3.0.0`, `python:3.13-slim`, and the QA Python venv with PyYAML/Playwright. Node tests need jsdom (installed outside repo in `/tmp/networking-node-qa`). QA binds only loopback port 18139 and removes its two named containers on exit. No playback/download activity.

Evidence `/srv/hermes/workspaces/networking-qa-evidence/networking-{390,1600}-{dark,light}.png`: **synthetic contract fixture, not live network**. Actual Go template renderer, native polling/SSE changed-fixture update, query/caret/disclosure preservation, theme/mobile overflow and 44px controls, zero/null differences, firewall available/unavailable, errors/empty states, sparse SVG circle and explicit axes checked. Screenshots retain synthetic labels; page shells show the full navigation, but non-NETWORKING widgets are intentionally fixture-only.

All styles anchor to `.nw-dashboard` because native custom-API HTML can fall through wrapper-free. Refresh uses only public `dynacat:widget-updated`, no extra timer. Both replaced inputs and retained SSE-morphed inputs preserve search selection.
