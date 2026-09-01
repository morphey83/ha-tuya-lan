# Brand icon

The icon (concept: a Wi‑Fi symbol whose origin is a keyhole — "a local key
unlocks local access") lives in [`brand/`](../brand):

| file | size | purpose |
|---|---|---|
| `icon.svg` | — | editable master |
| `icon.png` | 256×256 | what Home Assistant / HACS display |
| `icon@2x.png` | 512×512 | hi‑dpi variant |

Regenerate the PNGs after editing the SVG:

```bash
pip install pymupdf
python tools/render_icons.py
```

## Making it show up in Home Assistant

Home Assistant and HACS do **not** read the icon from this repo. They fetch it
from the central [`home-assistant/brands`](https://github.com/home-assistant/brands)
repository, keyed by the integration domain (`tuya_lan`). Until a brands PR is
merged, HACS shows a generic placeholder — this does not affect functionality.

To publish it, open a PR against `home-assistant/brands` adding:

```
custom_integrations/tuya_lan/icon.png       (256×256, from brand/icon.png)
custom_integrations/tuya_lan/icon@2x.png    (512×512, from brand/icon@2x.png)
```

Requirements the brands CI enforces: PNG with transparency, exact sizes, the
`@2x` file exactly double, trimmed so the graphic nearly fills the canvas.
A `logo.png` (wordmark) is optional and falls back to the icon.
