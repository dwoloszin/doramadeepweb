"""Cartelas do video (titulo do episodio / 'continua...') desenhadas com Pillow."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

from .config import FONTS

GOLD = (232, 200, 130)
WHITE = (255, 255, 255)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def cover(img: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * r + 0.5), int(img.height * r + 0.5)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def wrap(draw, text: str, f, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=f) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def spaced(draw, xy_center, text, f, fill, tracking: int):
    """Texto centralizado com espacamento entre letras (kicker)."""
    widths = [draw.textlength(c, font=f) for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = xy_center[0] - total / 2
    for c, cw in zip(text, widths):
        draw.text((x, xy_center[1]), c, font=f, fill=fill)
        x += cw + tracking


def ornament(draw, cx, y, half=170, color=GOLD):
    draw.line((cx - half, y, cx - 18, y), fill=color, width=2)
    draw.line((cx + 18, y, cx + half, y), fill=color, width=2)
    draw.regular_polygon((cx, y, 7), 4, rotation=45, fill=color)


SEAL_TEXT = "BASEADO EM FATOS REAIS"


def seal(img: Image.Image, cx: int, y: int, size: int, text: str = SEAL_TEXT) -> int:
    """Selo 'BASEADO EM FATOS REAIS' (pedido do autor, 14/11): pilula escura translucida com borda
    dourada, losangos nas pontas e letras espacadas. Devolve o y logo abaixo do selo."""
    f = font("Poppins-SemiBold.ttf", size)
    d = ImageDraw.Draw(img)
    trk = max(2, size // 5)
    tw = sum(d.textlength(c, font=f) for c in text) + trk * (len(text) - 1)
    padx, bh = int(size * 2.2), int(size * 2.2)
    bw = int(tw + 2 * padx)
    x0, y0 = int(cx - bw / 2), int(y)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    od.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), bh // 2, fill=(12, 9, 16, 185), outline=GOLD + (255,), width=2)
    base = img.convert("RGBA")
    base.alpha_composite(over)
    img.paste(base.convert("RGB"))
    d = ImageDraw.Draw(img)
    spaced(d, (cx, y0 + (bh - size * 1.3) / 2), text, f, GOLD, trk)
    for sx in (x0 + padx * 0.45, x0 + bw - padx * 0.45):  # losangos
        d.regular_polygon((sx, y0 + bh / 2, size * 0.32), 4, rotation=45, fill=GOLD)
    return y0 + bh


def card(bg: Path, kind: str, texts: dict, w: int, h: int, out: Path, series: str = "") -> Path:
    base = cover(Image.open(bg).convert("RGB"), w, h)
    base = base.filter(ImageFilter.GaussianBlur(14))
    base = ImageEnhance.Brightness(base).enhance(0.42)
    # gradiente escuro no centro para o texto respirar
    shade = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(shade)
    for y in range(h):
        d = abs(y - h * 0.45) / (h * 0.5)
        sd.line((0, y, w, y), fill=int(150 * max(0.0, 1 - d)))
    base = Image.composite(Image.new("RGB", (w, h), (8, 6, 12)), base, shade)
    d = ImageDraw.Draw(base)
    cx = w // 2
    if kind == "question":
        return _question(base, d, texts, w, h, out, series)
    y = int(h * 0.33)
    spaced(d, (cx, y), texts.get("kicker", ""), font("Poppins-SemiBold.ttf", 38), GOLD, 12)
    y += 90
    ornament(d, cx, y)
    y += 50
    ft = font("CormorantBold.ttf", 118 if kind == "title" else 130)
    for line in wrap(d, texts.get("title", ""), ft, w - 160):
        tw = d.textlength(line, font=ft)
        d.text((cx - tw / 2, y), line, font=ft, fill=WHITE)
        y += 128
    if texts.get("subtitle"):
        y += 10
        fs = font("CormorantSemiBoldItalic.ttf", 72 if kind == "title" else 48)
        for line in wrap(d, texts["subtitle"], fs, w - 200):
            tw = d.textlength(line, font=fs)
            d.text((cx - tw / 2, y), line, font=fs, fill=(240, 228, 210))
            y += 84 if kind == "title" else 60
    y += 40
    ornament(d, cx, y)
    if kind == "title":  # selo nos videos novos (Ep. 14+)
        seal(base, cx, y + 60, 30)
    if series:
        fser = font("Poppins-Regular.ttf", 30)
        spaced(d, (cx, int(h * 0.80)), series.upper(), fser, (200, 190, 175), 8)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=95)
    return out


def _question(base, d, texts: dict, w: int, h: int, out: Path, series: str) -> Path:
    """Cartela final com a PERGUNTA para o publico (engajamento nos comentarios)."""
    cx = w // 2
    y = int(h * 0.27)
    spaced(d, (cx, y), texts.get("kicker", "E VOCÊ?"), font("Poppins-SemiBold.ttf", 44), GOLD, 14)
    y += 96
    ornament(d, cx, y)
    y += 60
    ft = font("CormorantBold.ttf", 112)
    for line in wrap(d, texts.get("title", ""), ft, w - 150):
        d.text((cx - d.textlength(line, font=ft) / 2, y), line, font=ft, fill=WHITE)
        y += 120
    if texts.get("subtitle"):
        y += 24
        fs = font("CormorantSemiBoldItalic.ttf", 60)
        for line in wrap(d, texts["subtitle"], fs, w - 200):
            d.text((cx - d.textlength(line, font=fs) / 2, y), line, font=fs, fill=(240, 228, 210))
            y += 72
    y += 40
    ornament(d, cx, y)
    if texts.get("footer"):
        ff = font("Poppins-SemiBold.ttf", 34)
        spaced(d, (cx, int(h * 0.74)), texts["footer"].upper(), ff, GOLD, 8)
    if series:
        spaced(d, (cx, int(h * 0.80)), series.upper(), font("Poppins-Regular.ttf", 30), (200, 190, 175), 8)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=95)
    return out
