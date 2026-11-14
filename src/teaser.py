"""Teaser "ALERTA DE SPOILER" — divulgacao no meio da semana do PROXIMO episodio.

O autor assiste o episodio e diz qual momento quer usar; o roteiro fica no
epNN.yaml, bloco `teaser:` (uma lista; cada item vira um teaser):

  teaser:
    - id: t1
      from: s18                 # (a) um frame do proprio video ...
      zoom: 1.7                 #     1.0 = cena inteira; >1 = close (ex.: so o rosto)
      focus: [0.5, 0.42]        #     centro do recorte (x, y de 0 a 1 na imagem)
      # shot: {...}             # (b) ... OU uma imagem NOVA, como uma cena do episodio:
      #   day/location/cast/props/look/visual (mesmas regras de `shots`)
      badge: "ALERTA DE SPOILER"
      title: "O que aconteceu pra deixar o Davi **ASSIM**?"   # **x** = destaque amarelo
      footer: "Não perca o próximo episódio!"
      caption: |                # legenda do post (Instagram / TikTok / comunidade do YouTube)
        ...
    - id: t3
      style: poster             # CARTAZ "proximo episodio": numero + titulo, SEM historia
      from: s01                 # (normalmente a mesma imagem da capa, em outro recorte)
      zoom: 1.15
      badge: "PRÓXIMO EPISÓDIO"
      footer: "Estreia no próximo episódio · não perca!"

Saida em output/epNN/teaser/:
  <id>_story.png  1080x1920  (Story/Status/TikTok foto; texto fora da area da interface)
  <id>_feed.png   1080x1350  (post do feed / comunidade do YouTube)
  teaser.txt      as legendas, prontas para copiar
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import gemini_image
from .cards import font, seal
from .config import ROOT
from .story import bible, episode, shot_prompt

RED = (226, 35, 52)
YELLOW = (255, 214, 64)
WHITE = (255, 255, 255)
INK = (10, 8, 12)


def _source(ep_id: str, ep: dict, t: dict, out_dir: Path, force: bool) -> Path:
    if t.get("shot"):
        shot = {"id": t["id"], **t["shot"]}
        prompt, refs = shot_prompt(bible(), ep, shot)
        out = out_dir / f"{t['id']}_src.png"
        print(f"  [teaser] {t['id']}: imagem nova (Gemini, na hora)")
        gemini_image.generate(prompt, out, refs=refs, aspect="9:16", force=force, image_size="2K")
        return out
    src = ROOT / "output" / ep_id / "frames" / f"{t['from']}.png"
    if not src.exists():
        raise FileNotFoundError(f"{src} nao existe (rode `python main.py frames {ep_id}`)")
    return src


def _crop(img: Image.Image, w: int, h: int, zoom: float, focus, place: float = 0.34) -> Image.Image:
    """Recorte w:h com zoom; o ponto `focus` (x, y em 0..1 da imagem) cai na altura `place`
    do quadro final (terco de cima), deixando a base livre para o titulo."""
    fx, fy = (focus if isinstance(focus, (list, tuple)) else (0.5, focus))
    r = max(w / img.width, h / img.height) * max(1.0, zoom)
    img = img.resize((int(img.width * r + 0.5), int(img.height * r + 0.5)), Image.LANCZOS)
    x = int(min(max(0, img.width * fx - w / 2), img.width - w))
    y = int(min(max(0, img.height * fy - h * place), img.height - h))
    out = img.crop((x, y, x + w, y + h))
    if zoom > 1.25:  # close muito ampliado: devolve um pouco de nitidez
        out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    return out


def _shade(base: Image.Image, top: float, bottom: float) -> Image.Image:
    """Escurece o topo (selo) e a base (titulo) para o texto ler bem."""
    w, h = base.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    for y in range(h):
        p = y / h
        a = 0.0
        if p < top:
            a = 0.62 * (1 - p / top) ** 1.4
        if p > bottom:
            a = max(a, 0.92 * ((p - bottom) / (1 - bottom)) ** 1.1)
        d.line((0, y, w, y), fill=int(255 * a))
    return Image.composite(Image.new("RGB", (w, h), INK), base, mask)


def _words(title: str):
    """'O que ... **ASSIM**?' -> [(palavra, destaque?)]"""
    out = []
    for m in re.finditer(r"\*\*(.+?)\*\*|([^*]+)", title):
        hi = bool(m.group(1))
        for w in (m.group(1) or m.group(2)).split():
            out.append((w, hi))
    return out


def _title_lines(d, words, f, max_w):
    lines, cur, cur_w = [], [], 0.0
    sp = d.textlength(" ", font=f)
    for w, hi in words:
        ww = d.textlength(w, font=f)
        if cur and cur_w + sp + ww > max_w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur_w += (sp if cur else 0) + ww
        cur.append((w, hi))
    if cur:
        lines.append(cur)
    return lines


def _badge(img: Image.Image, cx: int, y: int, text: str, size: int) -> int:
    d = ImageDraw.Draw(img)
    f = font("Poppins-Black.ttf", size)
    label = text.upper()  # Poppins nao tem emoji: as "sirenes" sao desenhadas
    tw = d.textlength(label, font=f)
    padx, pady = int(size * 0.9), int(size * 0.45)
    bw, bh = int(tw + 2 * padx), int(size * 1.25 + 2 * pady)
    x0 = cx - bw // 2
    # sombra + pilula vermelha + sirenes (triangulos) dos lados
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x0 + 6, y + 10, x0 + bw + 6, y + bh + 10), bh // 2, fill=(0, 0, 0, 150))
    img.paste(sh.filter(ImageFilter.GaussianBlur(10)), (0, 0), sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x0, y, x0 + bw, y + bh), bh // 2, fill=RED, outline=WHITE, width=4)
    d.text((cx - tw / 2, y + pady - size * 0.08), label, font=f, fill=WHITE)
    for sx in (x0 - 34 - size // 2, x0 + bw + 34):
        t = size * 0.95
        d.polygon([(sx + t / 2, y + bh / 2 - t / 2), (sx + t, y + bh / 2 + t / 2), (sx, y + bh / 2 + t / 2)],
                  fill=YELLOW, outline=INK)
        d.text((sx + t / 2 - size * 0.11, y + bh / 2 - t * 0.22), "!", font=font("Poppins-Black.ttf", int(size * 0.62)), fill=INK)
    return y + bh


def _compose(src: Path, t: dict, w: int, h: int, out: Path, *, safe_top: int, safe_bottom: int,
             title_size: int, series: str, place: float) -> Path:
    img = Image.open(src).convert("RGB")
    base = _crop(img, w, h, float(t.get("zoom", 1.0)), t.get("focus", [0.5, 0.45]), place)
    base = ImageEnhance.Contrast(base).enhance(1.06)
    base = _shade(base, top=0.22, bottom=0.52)
    d = ImageDraw.Draw(base)
    cx = w // 2

    # selo no topo
    yb = _badge(base, cx, safe_top, t.get("badge", "ALERTA DE SPOILER"), int(w * 0.042))
    seal(base, cx, yb + int(w * 0.022), int(w * 0.029))

    # titulo (Poppins Black, palavra em destaque amarela), de baixo para cima
    max_w = int(w * 0.84)
    size = title_size
    words = _words(t.get("title", ""))
    while True:
        f = font("Poppins-Black.ttf", size)
        lines = _title_lines(d, words, f, max_w)
        if len(lines) <= 4 or size < 50:
            break
        size -= 4
    lh = int(size * 1.12)
    ff = font("Poppins-SemiBold.ttf", int(w * 0.036))
    fs = font("Poppins-Regular.ttf", int(w * 0.024))
    footer = t.get("footer", "Não perca o próximo episódio!")
    y_series = h - safe_bottom - int(w * 0.03)
    y_footer = y_series - int(w * 0.075)
    y = y_footer - int(w * 0.05) - lh * len(lines)
    sp = d.textlength(" ", font=f)
    for line in lines:
        lw = sum(d.textlength(wd, font=f) for wd, _ in line) + sp * (len(line) - 1)
        x = cx - lw / 2
        for wd, hi in line:
            d.text((x, y), wd, font=f, fill=YELLOW if hi else WHITE,
                   stroke_width=max(3, size // 18), stroke_fill=INK)
            x += d.textlength(wd, font=f) + sp
        y += lh
    # rodape: chamada + nome da serie
    fw = d.textlength(footer, font=ff)
    d.text((cx - fw / 2, y_footer), footer, font=ff, fill=YELLOW, stroke_width=3, stroke_fill=INK)
    s = series.upper()
    trk = 6
    sw = sum(d.textlength(c, font=fs) for c in s) + trk * (len(s) - 1)
    x = cx - sw / 2
    for c in s:
        d.text((x, y_series), c, font=fs, fill=(225, 220, 210))
        x += d.textlength(c, font=fs) + trk
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=95)
    return out


def _poster(src: Path, t: dict, ep: dict, w: int, h: int, out: Path, *, safe_top: int,
            safe_bottom: int, title_size: int, series: str, place: float) -> Path:
    """Cartaz "PROXIMO EPISODIO": imagem + numero + titulo, SEM historia.
    Diferente da capa do carrossel de proposito (sem gancho, sem 'deslize para ler',
    selo dourado no topo, imagem em outro recorte) para nao confundir o leitor."""
    from .cards import GOLD, ornament, spaced, wrap
    img = Image.open(src).convert("RGB")
    base = _crop(img, w, h, float(t.get("zoom", 1.15)), t.get("focus", [0.5, 0.40]), place)
    base = ImageEnhance.Color(base).enhance(0.9)
    base = _shade(base, top=0.20, bottom=0.40)
    # vinheta lateral suave (ar de cartaz de cinema)
    vig = Image.new("L", (w, h), 0)
    dv = ImageDraw.Draw(vig)
    for i in range(60):
        a = int(150 * (1 - i / 60) ** 2)
        dv.rectangle((i * 3, i * 3, w - i * 3, h - i * 3), outline=a, width=3)
    base = Image.composite(Image.new("RGB", (w, h), INK), base, vig)
    d = ImageDraw.Draw(base)
    cx = w // 2

    # selo no topo: pilula escura com borda dourada
    fb = font("Poppins-Bold.ttf", int(w * 0.03))
    label = t.get("badge", "PRÓXIMO EPISÓDIO").upper()
    trk = 6
    tw = sum(d.textlength(c, font=fb) for c in label) + trk * (len(label) - 1)
    bw, bh = int(tw + w * 0.09), int(w * 0.075)
    x0, y0 = cx - bw // 2, safe_top
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), bh // 2, fill=(20, 16, 22), outline=GOLD, width=3)
    spaced(d, (cx, y0 + (bh - fb.size * 1.25) / 2), label, fb, GOLD, trk)
    seal(base, cx, y0 + bh + int(w * 0.02), int(w * 0.029))
    d = ImageDraw.Draw(base)

    # bloco de baixo: EPISODIO N / ornamento / titulo / estreia / serie
    fk = font("Poppins-SemiBold.ttf", int(w * 0.034))
    ft = font("CormorantBold.ttf", title_size)
    title = t.get("title") or ep["title"]
    lines = wrap(d, title, ft, int(w * 0.84))
    while len(lines) > 4 and ft.size > 50:
        ft = font("CormorantBold.ttf", ft.size - 6)
        lines = wrap(d, title, ft, int(w * 0.84))
    lh = int(ft.size * 1.04)
    ff = font("Poppins-SemiBold.ttf", int(w * 0.034))
    fs = font("Poppins-Regular.ttf", int(w * 0.024))
    y_series = h - safe_bottom - int(w * 0.03)
    y_footer = y_series - int(w * 0.075)
    y_title = y_footer - int(w * 0.07) - lh * len(lines)
    y_orn = y_title - int(w * 0.035)
    y_kick = y_orn - int(w * 0.075)
    kick = t.get("kicker", f"EPISÓDIO {ep['number']}")
    for dx, dy in ((-2, 2), (2, 2), (0, 3), (2, -1), (-2, -1)):
        spaced(d, (cx + dx, y_kick + dy), kick, fk, INK, 12)  # contorno p/ ler sobre fundo claro
    spaced(d, (cx, y_kick), kick, fk, GOLD, 12)
    ornament(d, cx, y_orn, int(w * 0.14))
    y = y_title
    for line in lines:
        d.text((cx - d.textlength(line, font=ft) / 2, y), line, font=ft, fill=WHITE,
               stroke_width=2, stroke_fill=INK)
        y += lh
    footer = t.get("footer", "Estreia no próximo episódio · não perca!")
    d.text((cx - d.textlength(footer, font=ff) / 2, y_footer), footer, font=ff, fill=YELLOW,
           stroke_width=3, stroke_fill=INK)
    s = series.upper()
    sw = sum(d.textlength(c, font=fs) for c in s) + 6 * (len(s) - 1)
    x = cx - sw / 2
    for c in s:
        d.text((x, y_series), c, font=fs, fill=(225, 220, 210))
        x += d.textlength(c, font=fs) + 6
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=95)
    return out


def build(ep_id: str, only: list[str] | None = None, force: bool = False) -> list[Path]:
    ep = episode(ep_id)
    items = ep.get("teaser") or []
    if not items:
        raise SystemExit(f"{ep_id}: sem bloco `teaser:` no story/{ep_id}.yaml")
    series = bible()["series"]["title"]
    out_dir = ROOT / "output" / ep_id / "teaser"
    made = []
    # legendas de TODOS os teasers (mesmo quando so um foi refeito)
    from .calendario import quando  # mesmas datas do YouTube/Instagram (schedule.yaml)
    txt = [f"===== {t['id']} — POSTAR: {quando(ep_id, t['id'])} — arquivo: {t['id']}_short.mp4 (video com voz) ou {t['id']}_story.png (foto) =====\n"
           f"{(t.get('caption') or '').strip()}\n"
           for t in items]
    for t in items:
        if only and t["id"] not in only:
            continue
        src = _source(ep_id, ep, t, out_dir, force)
        if t.get("style") == "poster":
            made.append(_poster(src, t, ep, 1080, 1920, out_dir / f"{t['id']}_story.png",
                                safe_top=250, safe_bottom=320, title_size=100, series=series, place=0.27))
            made.append(_poster(src, t, ep, 1080, 1350, out_dir / f"{t['id']}_feed.png",
                                safe_top=60, safe_bottom=50, title_size=70, series=series, place=0.24))
            print(f"  [teaser] {t['id']} (cartaz) -> {out_dir}")
            continue
        # Story 9:16: interface do Instagram/TikTok cobre ~250px no topo e ~380px na base
        made.append(_compose(src, t, 1080, 1920, out_dir / f"{t['id']}_story.png",
                             safe_top=250, safe_bottom=320, title_size=92, series=series, place=0.30))
        made.append(_compose(src, t, 1080, 1350, out_dir / f"{t['id']}_feed.png",
                             safe_top=70, safe_bottom=60, title_size=66, series=series, place=0.34))
        print(f"  [teaser] {t['id']} -> {out_dir}")
    if txt:
        (out_dir / "teaser.txt").write_text("\n".join(txt), encoding="utf-8")
    return made
