# Pi-hole history frontend QA

Supersedes previous DNS-list/client-layout acceptance.

- Native tests: 4 passed, with separate observed RED/GREEN for removal/full-width and combined chart replacement.
- Backend+wiring: 220 passed, 92 subtests passed. Exact timestamp sums, privacy, null gaps, missing instances, official endpoint and compact UTC labels covered.
- Production code release: `7900c2a60826f525638e918646f82503eaf10aa8`, deployed through Git/Komodo; all five services running, health-enabled collector and geoip healthy, Komodo running(5), no remote errors.
- Live and captured-real native screenshots at 1600/390, dark/light: all passed; mobile contexts have touch and mobile emulation. Actual swipes and scroll stability through refresh checked. Wait for touch inertia before comparing scroll positions.
- Exact captured backend line/area paths match native SVG for both series. Retained infrastructure paths also match captured real source. No clients or domain lists, no overflow or JS errors. Pi-hole width1534 desktop /348 mobile matches infrastructure.
- Actual query series have 600-second resolution, three actual source points in last30minutes. Blank edges are not fabricated backfill. Both sources available.
- Live screenshots visually inspected for readable short UTC endpoints, sensible stats wrapping, distinguishable shaded series in both themes.

Artifacts untracked under `networking-query-qa/`: `live-{dark,light}-{1600,390}-{page,pihole}.png`, corresponding candidate captures and report JSON. Source `/tmp/network-query-current.json` is captured production JSON with client inventory removed; Pi-hole no longer exports domain records.

Run `/srv/hermes/workspaces/dynacat-qa-venv/bin/python tools/dynacat/qa_networking_lower.py` for captured-real native QA, or add `--url http://127.0.0.1:18148/networking` for production via read-only SSH tunnel. Live QA waits up to30seconds for existing demand-cache refresh rather than declaring its initial unavailable response a permanent failure. No audio playback, Pi-hole changes, volume removal or direct service restart.
