"""Carrossel do capitulo (Instagram 4:5, 1080x1350) — o episodio como livro.

Cada slide: a imagem da cena no topo, dissolvendo num fundo escuro onde o
texto corre em Lora (serifa de romance). **negrito** = fala/impacto,
_italico_ = pensamento. A fonte se ajusta sozinha para o texto caber.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .cards import GOLD, cover, font, ornament, seal, spaced, wrap
from .config import ROOT
from .story import bible, episode

W, H = 1080, 1350
INK = (14, 11, 16)
TEXT = (238, 232, 222)
THOUGHT = (214, 196, 232)
MARGIN = 92


def _bg(img_path: Path, fade_from: float = 0.30, fade_to: float = 0.62, dim: float = 1.0,
        focus: float = 0.45, anchor: float | None = None) -> Image.Image:
    src = Image.open(img_path).convert("RGB")
    # imagem 9:16 -> recorte 4:5 puxado para cima (rostos ficam no terco superior)
    r = W / src.width
    src = src.resize((W, int(src.height * r)), Image.LANCZOS)
    # o ponto `focus` da imagem (0=topo, 1=base) cai no meio da area visivel
    anchor = anchor if anchor is not None else H * fade_from * 0.95
    top = int(min(max(0, src.height * focus - anchor), src.height - H))
    base = src.crop((0, top, W, top + H))
    if dim < 1:
        base = Image.blend(Image.new("RGB", (W, H), INK), base, dim)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    for y in range(H):
        p = (y / H - fade_from) / (fade_to - fade_from)
        d.line((0, y, W, y), fill=int(255 * min(1, max(0, p)) ** 0.9))
    return Image.composite(Image.new("RGB", (W, H), INK), base, mask)


def _runs(paragraph: str):
    """'texto **forte** _pensa_' -> [(style, word), ...]"""
    out = []
    for m in re.finditer(r"\*\*(.+?)\*\*|_(.+?)_|([^*_]+)", paragraph):
        style = "bold" if m.group(1) else "ital" if m.group(2) else "reg"
        for w in (m.group(1) or m.group(2) or m.group(3)).split():
            out.append((style, w))
    return out


def _fonts(size: int):
    return {"reg": font("LoraRegular.ttf", size), "bold": font("LoraSemiBold.ttf", size),
            "ital": font("LoraItalic.ttf", size)}


def _layout(text: str, size: int, max_w: int):
    """Linhas de [(style, word)] + altura total."""
    fs = _fonts(size)
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines, lh, gap = [], int(size * 1.52), int(size * 0.75)
    height = 0
    for para in [p.strip() for p in text.strip().split("\n\n") if p.strip()]:
        cur, cur_w = [], 0.0
        for style, w in _runs(para):
            ww = d.textlength(w, font=fs[style])
            sp = d.textlength(" ", font=fs[style])
            if cur and cur_w + sp + ww > max_w:
                lines.append(cur)
                height += lh
                cur, cur_w = [], 0.0
            cur_w += (sp if cur else 0) + ww
            cur.append((style, w))
        if cur:
            lines.append(cur)
            height += lh
        lines.append(None)  # quebra de paragrafo
        height += gap
    return lines, height - gap, lh, gap, fs


def _draw_text(img: Image.Image, text: str, box: tuple[int, int, int, int], start: int = 50):
    x0, y0, x1, y1 = box
    size = start
    while size > 30:
        lines, h, lh, gap, fs = _layout(text, size, x1 - x0)
        if h <= y1 - y0:
            break
        size -= 2
    d = ImageDraw.Draw(img)
    y = y1 - h  # texto ancorado embaixo (perto do polegar), a imagem respira em cima
    y = max(y0, y - 0)
    for ln in lines:
        if ln is None:
            y += gap
            continue
        x = x0
        for style, w in ln:
            col = THOUGHT if style == "ital" else (255, 255, 255) if style == "bold" else TEXT
            d.text((x, y), w, font=fs[style], fill=col)
            x += d.textlength(w + " ", font=fs[style])
        y += lh
    return size


def _arrow(d, x, y, color, length=34):
    d.line((x, y, x + length, y), fill=color, width=3)
    d.line((x + length - 10, y - 8, x + length, y), fill=color, width=3)
    d.line((x + length - 10, y + 8, x + length, y), fill=color, width=3)


def _chrome(img: Image.Image, idx: int, total: int, chapter: int, last: bool):
    d = ImageDraw.Draw(img)
    spaced(d, (W // 2, 54), f"CAPÍTULO {chapter}", font("Poppins-SemiBold.ttf", 24), GOLD, 7)
    # pontos de progresso
    n = total
    dot, gapx = 9, 22
    x = W // 2 - (n - 1) * gapx // 2
    for i in range(n):
        c = GOLD if i == idx else (110, 100, 95)
        r = dot // 2 + (2 if i == idx else 0)
        d.ellipse((x - r, H - 58 - r, x + r, H - 58 + r), fill=c)
        x += gapx
    if not last:
        f = font("Poppins-Regular.ttf", 24)
        t = "deslize"
        tx = W - MARGIN - 46 - d.textlength(t, font=f)
        d.text((tx, H - 72), t, font=f, fill=(190, 180, 170))
        _arrow(d, W - MARGIN - 36, H - 57, (190, 180, 170))


def build(ep_id: str) -> list[Path]:
    b, ep = bible(), episode(ep_id)
    frames = ROOT / "output" / ep_id / "frames"
    out_dir = ROOT / "output" / ep_id / "carousel"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    slides = ep["carousel"]
    total = len(slides)
    paths = []
    for i, s in enumerate(slides):
        kind = s.get("type", "text")
        if kind == "cover":
            img = _bg(frames / f"{s['bg']}.png", 0.42, 0.80, focus=s.get("focus", 0.3), anchor=330)
            d = ImageDraw.Draw(img)
            spaced(d, (W // 2, 760), s.get("kicker", ""), font("Poppins-SemiBold.ttf", 30), GOLD, 10)
            ornament(d, W // 2, 830, 150)
            ft = font("CormorantBold.ttf", 92)
            y = 870
            for line in wrap(d, s["title"], ft, W - 2 * MARGIN):
                d.text((W // 2 - d.textlength(line, font=ft) / 2, y), line, font=ft, fill=(255, 255, 255))
                y += 96
            fh = font("LoraItalic.ttf", 38)
            y += 26
            for line in wrap(d, s.get("hook", ""), fh, W - 2 * MARGIN - 40):
                d.text((W // 2 - d.textlength(line, font=fh) / 2, y), line, font=fh, fill=THOUGHT)
                y += 54
            fser = font("Poppins-Regular.ttf", 22)
            spaced(d, (W // 2, 40), b["series"]["title"].upper(), fser, (225, 215, 200), 8)
            seal(img, W // 2, 88, 22)
            d = ImageDraw.Draw(img)
            f = font("Poppins-SemiBold.ttf", 26)
            t = "deslize para ler"
            tw = d.textlength(t, font=f)
            d.text((W // 2 - (tw + 50) / 2, H - 92), t, font=f, fill=GOLD)
            _arrow(d, int(W // 2 - (tw + 50) / 2 + tw + 14), H - 76, GOLD)
        elif kind == "end":
            img = _bg(frames / f"{s['bg']}.png", 0.18, 0.55, focus=s.get("focus", 0.45), anchor=260)
            d = ImageDraw.Draw(img)
            fb = font("LoraSemiBold.ttf", 104)
            t = s.get("big", "")
            d.text((W // 2 - d.textlength(t, font=fb) / 2, 610), t, font=fb, fill=(255, 255, 255))
            ornament(d, W // 2, 770, 150)
            _draw_text(img, s.get("text", ""), (MARGIN + 20, 800, W - MARGIN - 20, 1080), 44)
            fc = font("Poppins-SemiBold.ttf", 26)
            for k, line in enumerate(wrap(d, s.get("cta", ""), fc, W - 2 * MARGIN)):
                d.text((W // 2 - d.textlength(line, font=fc) / 2, 1140 + k * 40), line, font=fc, fill=GOLD)
            _chrome(img, i, total, ep["number"], True)
        elif kind == "question":
            # pergunta final: puxa o leitor para os comentarios
            img = _bg(frames / f"{s['bg']}.png", 0.16, 0.50, focus=s.get("focus", 0.45), anchor=260)
            d = ImageDraw.Draw(img)
            spaced(d, (W // 2, 560), s.get("kicker", "E VOCÊ?"), font("Poppins-SemiBold.ttf", 34), GOLD, 12)
            ornament(d, W // 2, 625, 150)
            ft = font("CormorantBold.ttf", 86)
            y = 665
            for line in wrap(d, s["title"], ft, W - 2 * MARGIN):
                d.text((W // 2 - d.textlength(line, font=ft) / 2, y), line, font=ft, fill=(255, 255, 255))
                y += 92
            _draw_text(img, s.get("text", ""), (MARGIN + 20, y + 30, W - MARGIN - 20, 1150), 42)
            fc = font("Poppins-SemiBold.ttf", 26)
            for k, line in enumerate(wrap(d, s.get("cta", ""), fc, W - 2 * MARGIN)):
                d.text((W // 2 - d.textlength(line, font=fc) / 2, 1170 + k * 40), line, font=fc, fill=GOLD)
            _chrome(img, i, total, ep["number"], True)
        else:
            img = _bg(frames / f"{s['bg']}.png", 0.30, 0.52, focus=s.get("focus", 0.45))
            _draw_text(img, s["text"], (MARGIN, 560, W - MARGIN, H - 130), 48)
            _chrome(img, i, total, ep["number"], False)
        if kind == "cover":
            pass
        p = out_dir / f"{ep_id}_{i + 1:02d}.jpg"
        img.save(p, quality=93)
        paths.append(p)
    cap = ep.get("publish", {}).get("instagram_caption", "")
    (out_dir / "caption.txt").write_text(cap, encoding="utf-8")
    tt = ep.get("publish", {}).get("tiktok_caption", "")
    if tt:  # TikTok e manual: legenda do VIDEO pronta para colar (output/epNN/tiktok.txt)
        (out_dir.parent / "tiktok.txt").write_text(tt.strip() + "\n", encoding="utf-8")
    print(f"carrossel: {len(paths)} slides em {out_dir}")
    return paths
