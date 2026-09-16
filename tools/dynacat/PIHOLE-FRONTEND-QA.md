# Pi-hole frontend verification

## Scope / acceptance

- [x] Available + partial renders actionable warning and labels totals as partial.
- [x] Partial without an error has a partial-specific fallback, not a full-outage claim.
- [x] Fully available uses `Across both instances.`; gravity sum is explicitly not deduplicated.
- [x] Native history uses `Permitted DNS queries`, never claims successful resolution, and preserves provider status and source identity.
- [x] Native renderer limits each supplied merged history to ten records.
- [x] Expanded clients-left layout, filter refresh and mobile stacking remain covered.
- [x] No CSS edits; infrastructure and client template bytes preserved.
- [ ] Captured-real available Pi-hole screenshots in desktop/mobile and light/dark after deployment (release owner).

## Reproducible native regression command

From repository root:

```sh
/srv/hermes/workspaces/dynacat-qa-venv/bin/python -m pytest tools/dynacat/test_networking_lower.py -q --tb=short
```

Uses Docker Dynacat 3.0.0, existing captured UniFi response and **synthetic** Pi-hole states, a local read-only fixture HTTP server, production head/assets, and actual native widget polling. Does not deploy. Docker network `media-compact-qa` and the existing `networking-layout-qa/source/network-current` capture are prerequisites. Do not run concurrently with the other networking QA harness: its source container name is shared.

TDD evidence: `-k partial -q` initially failed with `.nw-warning` absent despite `available=true`. After the minimal conditional/totals fix it passed (1 passed). Parameterizing the empty-error case then failed because the fallback incorrectly claimed complete integration unavailability. After its minimal fallback fix the full suite passed (9 passed). Existing permitted/non-deduplicated wording needed no production change; assertions protect that existing behavior.

## Live verification handoff

The existing `qa_networking_lower.py --url URL` captures full-page and lower-panel PNGs plus report JSON in `networking-lower-qa/`. It disables media `play()`, but only resizes its page; **do not present that alone as touch/mobile-emulation acceptance**. For complete live QA reuse the context/route guard from `qa_networking_layout.py`: independent contexts for widths 1600/390, `is_mobile` and `has_touch` true at 390, and block media, stream/radio and cross-origin requests. That older layout script's main inspection still expects the removed clients disclosure, so do not run it unchanged.

Capture native rendered live data; never replace live histories with the synthetic test fixture. Check Pi-hole totals against the same captured adapter response, both instance names/states, ten permitted/blocked rows when supplied, exact source/status/time ordering, warning visibility for actual partial data, no overflow or JS errors, client filter and uninterrupted mobile scroll through native refreshes. Review screenshots visually. Do not start audio, modify Pi-hole settings, or imply available-data screenshots prove a synthetic partial-state outage occurred in production.
