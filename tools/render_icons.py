#!/usr/bin/env python3
"""Rasterise brand/icon.svg into the PNGs the home-assistant/brands repo wants.

    python tools/render_icons.py

Needs `pymupdf` (`pip install pymupdf`). Outputs into brand/:
  icon.png       256x256
  icon@2x.png    512x512
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "brand" / "icon.svg"


def render(size: int, out: Path) -> None:
    doc = pymupdf.open(SRC)
    page = doc[0]
    scale = size / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
    pix.save(out)
    print(f"{out.name}: {pix.width}x{pix.height}")


def main() -> None:
    render(256, SRC.with_name("icon.png"))
    render(512, SRC.with_name("icon@2x.png"))


if __name__ == "__main__":
    main()
