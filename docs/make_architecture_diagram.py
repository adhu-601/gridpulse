"""Render docs/architecture.svg (the canonical, hand-crafted diagram) to PNG.

The SVG is the source of truth — edit it directly. This script only rasterises
it for contexts that can't display SVG (the PDF report, some previewers):

    pip install cairosvg
    python docs/make_architecture_diagram.py
"""

from pathlib import Path

import cairosvg

HERE = Path(__file__).resolve().parent
SVG = HERE / "architecture.svg"
PNG = HERE / "architecture.png"

cairosvg.svg2png(url=str(SVG), write_to=str(PNG), output_width=2340)
print(f"wrote {PNG}")
