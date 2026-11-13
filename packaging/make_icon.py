"""Generate a simple packaging/tally_sync.ico for the Windows build."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).resolve().parent / "tally_sync.ico"
image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.ellipse((16, 16, 240, 240), fill=(22, 163, 74, 255))
draw.rectangle((72, 110, 184, 146), fill=(255, 255, 255, 255))
image.save(out, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(out)
