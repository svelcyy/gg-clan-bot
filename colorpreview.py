"""Draws a preview of a custom role colour (solid or gradient), the way it looks in Discord.

Uses Pillow. If Pillow isn't installed the bot still works, just without the picture.
"""
from __future__ import annotations

import io

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None


def _rgb(c: int) -> tuple[int, int, int]:
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def _gradient(w: int, h: int, a: int, b: int | None) -> "Image.Image":
    ca, cb = _rgb(a), _rgb(b if b is not None else a)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        t = x / max(1, w - 1)
        col = tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
        for y in range(h):
            px[x, y] = col
    return img


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow
        return ImageFont.load_default()


def render(name: str, primary: int, secondary: int | None = None) -> io.BytesIO | None:
    """PNG bytes: the name written in the role colour on Discord's dark and light backgrounds, plus a swatch."""
    if Image is None:
        return None
    W, H = 640, 250
    card = Image.new("RGB", (W, H), (49, 51, 56))            # Discord dark theme
    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 125, W, H], fill=(255, 255, 255))      # light theme strip
    font, small = _font(46), _font(18)
    label = f"@{name}"[:24]
    for top, sub, subcol in ((28, "Dark theme", (148, 155, 164)), (153, "Light theme", (92, 94, 102))):
        box = draw.textbbox((0, 0), label, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        mask = Image.new("L", (tw + 4, th + 12), 0)
        ImageDraw.Draw(mask).text((-box[0], -box[1]), label, font=font, fill=255)
        card.paste(_gradient(mask.width, mask.height, primary, secondary), (30, top), mask)
        draw.text((32, top + th + 18), sub, font=small, fill=subcol)
    card.paste(_gradient(180, H, primary, secondary), (W - 180, 0))   # big colour swatch down the side
    out = io.BytesIO()
    card.save(out, "PNG")
    out.seek(0)
    return out


def parse_hex(text: str | None) -> int | None:
    """'#75117e', '75117e' or '#7a1' -> int. None if it isn't a colour."""
    if not text:
        return None
    t = text.strip().lstrip("#")
    if len(t) == 3:
        t = "".join(ch * 2 for ch in t)
    if len(t) != 6:
        return None
    try:
        return int(t, 16)
    except ValueError:
        return None
