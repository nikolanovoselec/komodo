# THE CONSTRUCT icon

The unmodified user-supplied `rRziaa.png` is vendored as `source-rRziaa.png`.
`provenance.json` records its SHA-256, dimensions, padding, resampling and output hashes.
The source is centered at `(0, 57)` on an opaque 869×869 canvas filled with its
original top-left navy pixel, RGB `(27, 31, 38)` / `#1b1f26`, then uniformly resized
with Pillow LANCZOS. No cropping, stretching, tracing or replacement artwork.

## Native integration

Verified against the actual `panonim/dynacat:3.0.0` image and upstream revision
`d67959b239a91ecd8288ee3b596f6685296127c2`:

- `branding.favicon-url` replaces the native favicon link with `icon-32.png`.
- `branding.app-icon-url` supplies `icon-512.png` to BOTH the native Apple touch
  link (explicitly 512×512) and generated manifest (also explicitly 512×512).
- `branding.app-background-color` matches the padded source background.
- Each image URL carries the first 12 characters of its SHA-256 as `?v=`.
- No additional icon links in `document.head`; no competing pink default icon,
  JavaScript link replacement, gateway substitutions, or duplicate manifest.
- Only 32×32 and 512×512 are needed by these native slots. Deliberately no unused
  16/180/192 files or ICO: this version hardcodes non-SVG favicon MIME to
  `image/png`, so wiring an ICO would incorrectly advertise its type.

Upstream references:
- https://github.com/Panonim/dynacat/blob/d67959b239a91ecd8288ee3b596f6685296127c2/internal/dynacat/templates/document.html
- https://github.com/Panonim/dynacat/blob/d67959b239a91ecd8288ee3b596f6685296127c2/internal/dynacat/templates/manifest.json
- https://github.com/Panonim/dynacat/blob/d67959b239a91ecd8288ee3b596f6685296127c2/internal/dynacat/dynacat.go

## Predeployment verification

From the repository root, with pytest, PyYAML and Pillow installed:

```sh
RUN_CONSTRUCT_ICON_NATIVE=1 python -m pytest -q -s \
  tools/dynacat/test_construct_icons.py \
  tools/dynacat/test_construct_icons_native.py
```

The native test starts an isolated, ephemeral local renderer using the existing
image, production branding/head and read-only assets. It substitutes only a
static QA page so no real backend polling occurs; cache goes to `/tmp/cache`.
It asserts exactly one favicon, touch icon and manifest link, checks the native
manifest and fetches both URLs to verify HTTP 200, PNG MIME and byte identity.
The container and generated QA config are removed in `finally`. No deployment,
production modification, commit or gateway change is performed.

Initial provenance and wiring tests failed as expected before implementation;
final verification: **3 passed**, including the real native renderer.
