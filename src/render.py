"""Monta o episodio: narracao -> linha do tempo -> clipes com camera -> mix final.

Linha do tempo: a cena i comeca em S_i (soma das duracoes anteriores). A
transicao PARA a cena i acontece em [S_i, S_i + c_i], entao o clipe i-1 e
renderizado com c_i segundos a mais. Assim o tempo das falas (e das legendas)
e simplesmente S_i + offset da fala — sem deriva.
"""
from __future__ import annotations

import json
import math
import random
import subprocess
from pathlib import Path

from PIL import Image

from . import cards, elevenlabs, ffmpeg, subs, tts
from .config import FONTS, ROOT, Config, load_config
from .story import bible, episode

XFADE = {"dissolve": "fade", "fadeblack": "fadeblack", "fadewhite": "fadewhite",
         "flash": "fadewhite", "cut": "fade"}

GRADE = {
    # dourado, leve bloom (sonho)
    "dream": ("split[a][b];[b]gblur=sigma=30[bb];[a][bb]blend=all_mode=softlight:all_opacity=0.35,"
              "eq=brightness=0.01:saturation=0.98:gamma=1.02,"
              "colorbalance=rm=0.015:gm=0.01:bm=-0.05:rh=0.02:gh=0.015:bh=-0.04"),
    # realidade: mais seca, contraste, verde-amarelado sujo
    "real": "eq=contrast=1.07:saturation=0.84,colorbalance=rs=-0.02:gs=0.02:bs=-0.02:rm=0.02:gm=0.025:bm=-0.03",
    # madrugada: fria
    "night": "eq=brightness=-0.02:saturation=0.85:contrast=1.05,colorbalance=rs=-0.03:bs=0.07:bm=0.04",
}


def _run_ff(args: list[str], cwd: Path | None = None, timeout: int = 1800) -> None:
    cmd = [ffmpeg.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"] + args
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg falhou:\n" + " ".join(cmd)[:1500] + "\n\n" + p.stderr[-3000:])


# --------------------------------------------------------------------------
# 1) narracao + linha do tempo
# --------------------------------------------------------------------------
def plan(ep_id: str, cfg: Config, retake: set | None = None) -> dict:
    retake = set(retake or ())
    ep = episode(ep_id)
    # Voz por episodio: `voices:` no epNN.yaml sobrescreve campos do config.yaml
    # (ex.: o pensamento mais grave a partir do Ep. 7 sem mudar os episodios antigos).
    voices = {k: dict(v) for k, v in cfg.get("voices").items()}
    for who, over in (ep.get("voices") or {}).items():
        base = voices.setdefault(who, {})
        for k, val in over.items():
            base[k] = {**base.get(k, {}), **val} if isinstance(val, dict) and isinstance(base.get(k), dict) else val
    work = ROOT / "output" / ep_id / "_work"
    tsec = cfg.get("video.transition_seconds", {})
    lead_default = float(cfg.get("video.lead_in", 0.35))
    tail = float(cfg.get("video.tail", 0.25))
    shots = []
    S = 0.0
    for sh in ep["shots"]:
        c_in = float(tsec.get(sh.get("transition", "dissolve"), 0.8))
        item = {"shot": sh, "start": S, "c_in": c_in, "lines": []}
        if sh.get("card") and not sh.get("lines"):
            dur = float(sh.get("duration", 3.5))
        else:
            t = max(float(sh.get("lead", lead_default)), c_in * 0.6)
            lns = sh.get("lines", [])
            spoken = tts.synth_shot(lns, voices, work / "tts", model=cfg.get("tts.model", "eleven_v3"),
                                    provider=cfg.get("tts.provider", "elevenlabs"),
                                    force=sh["id"] in retake,
                                    max_gap=float(cfg.get("tts.max_gap", 0.45))) if lns else []
            for ln, line in zip(lns, spoken):
                item["lines"].append({"line": line, "offset": t})
                t += line.duration + float(ln.get("pause", 0.3))
            dur = max(t + tail, float(sh.get("min_duration", sh.get("duration", 2.5))))
        item["dur"] = dur
        shots.append(item)
        S += dur
    for i, it in enumerate(shots):
        it["c_out"] = shots[i + 1]["c_in"] if i + 1 < len(shots) else 0.0
    return {"ep": ep, "shots": shots, "total": S}


# --------------------------------------------------------------------------
# 2) clipes de video
# --------------------------------------------------------------------------
def _ease(p: float) -> float:
    # quase linear, com entrada/saida suaves (camera de filme, nao de slideshow)
    return 0.5 - 0.5 * math.cos(math.pi * p) if p < 1 else 1.0


def _motion_box(motion: str, p: float, sw: int, sh: int, ratio: float):
    """Retorna (x0,y0,x1,y1) em pixels da fonte para o progresso p."""
    q = 0.25 * p + 0.75 * _ease(p)
    if motion == "push_in":
        z = 1.0 + 0.14 * q
    elif motion == "pull_out":
        z = 1.14 - 0.14 * q
    else:
        z = 1.13
    bw, bh = sw / z, sw / z / ratio
    if bh > sh:
        bh, bw = sh / z, sh / z * ratio
    cx, cy = sw / 2, sh * 0.44
    span_x, span_y = (sw - bw) / 2, (sh - bh) / 2
    if motion == "pan_left":
        cx = sw / 2 + span_x * (1 - 2 * q)
    elif motion == "pan_right":
        cx = sw / 2 - span_x * (1 - 2 * q)
    elif motion == "pan_down":
        cy = sh / 2 - span_y * (1 - 2 * q)
    elif motion == "pan_up":
        cy = sh / 2 + span_y * (1 - 2 * q)
    cx = min(max(cx, bw / 2), sw - bw / 2)
    cy = min(max(cy, bh / 2), sh - bh / 2)
    x0, y0 = max(0.0, cx - bw / 2), max(0.0, cy - bh / 2)
    return (x0, y0, min(float(sw), x0 + bw), min(float(sh), y0 + bh))


def _glitch(frame: Image.Image, k: int, rng: random.Random) -> Image.Image:
    import numpy as np
    a = np.asarray(frame).copy()
    dx = int((10 - k) * 6)
    a[:, :, 0] = np.roll(a[:, :, 0], dx, axis=1)
    a[:, :, 2] = np.roll(a[:, :, 2], -dx, axis=1)
    for _ in range(6):
        y = rng.randrange(0, a.shape[0] - 80)
        hgt = rng.randrange(10, 80)
        a[y:y + hgt] = np.roll(a[y:y + hgt], rng.randrange(-120, 120), axis=1)
    return Image.fromarray(a)


def render_clip(src: Path, dur: float, motion: str, look: str, out: Path, cfg: Config,
                glitch: bool = False) -> Path:
    W, H, fps = int(cfg.get("video.width")), int(cfg.get("video.height")), int(cfg.get("video.fps"))
    img = Image.open(src).convert("RGB")
    # fonte ~1.3x da saida: qualidade no zoom sem custo absurdo
    scale = (W * 1.3) / img.width
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    sw, sh = img.size
    n = max(1, int(round(dur * fps)))
    vf = GRADE.get(look, "")
    grain = int(cfg.get("video.grain", 0))
    extra = []
    if grain:
        extra.append(f"noise=alls={grain}:allf=t")
    if cfg.get("video.vignette", True):
        extra.append("vignette=angle=PI/5.5")
    vf = ",".join([x for x in [vf] + extra + ["format=yuv420p"] if x])
    cmd = [ffmpeg.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
           str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    rng = random.Random(7)
    try:
        for f in range(n):
            box = _motion_box(motion, f / max(1, n - 1), sw, sh, W / H)
            fr = img.resize((W, H), Image.BILINEAR, box=box)
            if glitch and f < 11:
                fr = _glitch(fr, f, rng)
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"clip {out.name}: {err[-1500:]}")
    return out


# --------------------------------------------------------------------------
# 2b) CHOQUE DE REALIDADE (card: shock) — o sonho congela, racha, estilhaca,
#     some num chiado e a realidade "bate" na tela tremendo.
# --------------------------------------------------------------------------
def _still(src: Path, motion: str, p: float, look: str, out: Path, cfg: Config) -> Image.Image:
    """Quadro exato (camera no progresso p) ja com a cor do look — casa com o clipe vizinho."""
    W, H = int(cfg.get("video.width")), int(cfg.get("video.height"))
    img = Image.open(src).convert("RGB")
    scale = (W * 1.3) / img.width
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    fr = img.resize((W, H), Image.BICUBIC, box=_motion_box(motion, p, img.width, img.height, W / H))
    raw = out.with_suffix(".raw.png")
    fr.save(raw)
    vf = GRADE.get(look, "") or "null"
    _run_ff(["-i", str(raw), "-vf", vf, str(out)])
    return Image.open(out).convert("RGB")


SHOCK_STYLES = ("shatter", "wake", "rewind", "burn", "glitch")


def _shock_alt(style: str, a: Image.Image, b: Image.Image, t: float, dur: float, f: int,
               W: int, H: int, rng: random.Random, zoom, chroma) -> Image.Image:
    """Estilos extras de choque de realidade (o padrao 'shatter' = espelho estilhacado).
      wake   — piscar/acordar: palpebras fecham sobre o sonho borrado e abrem na realidade
      rewind — fita VHS embolando: faixas de tracking, cor vazando, tela azul, realidade
      burn   — queima de filme: superexposicao, buracos queimando, flash branco, realidade
      glitch — o sonho se desfaz em pixels/blocos e se remonta como realidade"""
    import numpy as np
    from PIL import ImageDraw, ImageEnhance, ImageFilter
    q = t / max(dur, 1e-3)
    if style == "wake":
        # abertura das palpebras ao longo do tempo (1 = aberto, 0 = fechado)
        keys = [(0.0, 1.0), (0.30, 0.0), (0.42, 0.0), (0.58, 0.55), (0.68, 0.08), (0.80, 0.0), (1.0, 1.0)]
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t0 <= q <= t1:
                k = (q - t0) / max(t1 - t0, 1e-6)
                k = k * k * (3 - 2 * k)
                o = v0 + (v1 - v0) * k
                break
        src = a if q < 0.42 else b
        blur = 18 * min(1, q / 0.3) if q < 0.42 else 22 * max(0.0, 1 - (q - 0.42) / 0.5)
        fr = src.filter(ImageFilter.GaussianBlur(blur)) if blur > 0.5 else src
        if q < 0.42:
            fr = ImageEnhance.Brightness(fr).enhance(1 - 0.4 * min(1, q / 0.3))
        m = Image.new("L", (W, H), 0)
        eh = H * 0.62 * o
        if eh > 2:
            ImageDraw.Draw(m).ellipse((-W * 0.35, H * 0.45 - eh, W * 1.35, H * 0.45 + eh), fill=255)
            m = m.filter(ImageFilter.GaussianBlur(60))
        return Image.composite(fr, Image.new("RGB", (W, H), (0, 0, 0)), m)
    if style == "rewind":
        if q < 0.62:
            e = q / 0.62
            arr = np.asarray(zoom(a, 1.0 + 0.1 * e)).copy()
            for _ in range(int(4 + 14 * e)):                     # faixas que escorregam
                y0 = rng.randrange(0, H - 40)
                hgt = rng.randrange(8, 40)
                arr[y0:y0 + hgt] = np.roll(arr[y0:y0 + hgt], rng.randint(-int(160 * e) - 10, int(160 * e) + 10), axis=1)
            band = int((q * 3.3 % 1.0) * H)                        # faixa de tracking rolando
            noise = (np.random.default_rng(f).random((60, W)) * 255).astype(np.uint8)
            arr[band:band + 60] = np.maximum(arr[band:band + 60] // 3, noise[: max(0, min(60, H - band)), :, None])
            arr[::3] = (arr[::3] * 0.7).astype(np.uint8)             # linhas de varredura
            fr = chroma(Image.fromarray(arr), int(6 + 26 * e))
            return ImageEnhance.Color(fr).enhance(1 + 0.8 * e)
        if q < 0.74:                                               # a tela azul do video cassete
            return Image.new("RGB", (W, H), (18, 40, 190))
        u = (q - 0.74) / 0.26
        k = math.exp(-4 * u)
        arr = np.asarray(b).copy()
        for _ in range(int(8 * k)):
            y0 = rng.randrange(0, H - 20)
            arr[y0:y0 + 14] = np.roll(arr[y0:y0 + 14], rng.randint(-40, 40), axis=1)
        return chroma(ImageEnhance.Brightness(Image.fromarray(arr)).enhance(1 + 0.5 * k), int(14 * k))
    if style == "burn":
        if q < 0.56:
            e = q / 0.56
            fr = ImageEnhance.Brightness(zoom(a, 1.0 + 0.05 * e)).enhance(1 + 1.1 * e)
            warm = Image.new("RGB", (W, H), (255, 140, 40))
            fr = Image.blend(fr, warm, 0.25 * e)
            m = Image.new("L", (W, H), 0)
            d = ImageDraw.Draw(m)
            r2 = random.Random(7)
            for _ in range(7):                                     # buracos queimando
                cx, cy = r2.uniform(0, W), r2.uniform(0, H)
                r = (e ** 1.6) * r2.uniform(250, 900)
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
            glow = m.filter(ImageFilter.GaussianBlur(45))
            fr = Image.composite(Image.new("RGB", (W, H), (255, 190, 90)), fr, glow)
            return Image.composite(Image.new("RGB", (W, H), (255, 252, 240)), fr, m.filter(ImageFilter.GaussianBlur(12)))
        if q < 0.66:
            return Image.new("RGB", (W, H), (255, 252, 240))
        u = (q - 0.66) / 0.34
        k = math.exp(-4.5 * u)
        fr = zoom(b, 1.0 + 0.08 * k)
        return Image.blend(fr, Image.new("RGB", (W, H), (255, 252, 240)), 0.85 * k)
    if style == "glitch":
        src, e = (a, q / 0.55) if q < 0.55 else (b, 1 - (q - 0.55) / 0.45)
        e = max(0.0, min(1.0, e))
        blk = max(1, int(2 + 110 * e ** 1.5))
        small = src.resize((max(1, W // blk), max(1, H // blk)), Image.BILINEAR)
        fr = small.resize((W, H), Image.NEAREST)
        arr = np.asarray(fr).copy()
        for _ in range(int(12 * e)):                               # blocos deslocados
            bw, bh = rng.randrange(80, 400), rng.randrange(20, 160)
            x0, y0 = rng.randrange(0, W - bw), rng.randrange(0, H - bh)
            dx = rng.randint(-120, 120)
            arr[y0:y0 + bh, x0:x0 + bw] = np.roll(arr[y0:y0 + bh, x0:x0 + bw], dx, axis=1)
        fr = chroma(Image.fromarray(arr), int(30 * e))
        if 0.52 < q < 0.58:
            fr = Image.blend(fr, Image.new("RGB", (W, H), (255, 255, 255)), 0.5)
        return fr
    raise ValueError(f"estilo de choque desconhecido: {style} (use {', '.join(SHOCK_STYLES)})")


def render_shock(src_from: Path, src_to: Path, dur: float, out: Path, cfg: Config, *,
                 motion_from: str, motion_to: str, look_from: str, look_to: str,
                 style: str = "shatter") -> Path:
    import numpy as np
    from PIL import ImageDraw, ImageEnhance
    W, H, fps = int(cfg.get("video.width")), int(cfg.get("video.height")), int(cfg.get("video.fps"))
    a = _still(src_from, motion_from, 1.0, look_from, out.with_name(out.stem + "_a.png"), cfg)
    b = _still(src_to, motion_to, 0.0, look_to, out.with_name(out.stem + "_b.png"), cfg)
    rng = random.Random(42)
    n = max(1, int(round(dur * fps)))
    tA, tB, tC = 0.32, 0.82, 1.0          # fim de: racha | estilhaca | chiado ; depois: realidade
    cx, cy = W * 0.5, H * 0.42
    K, radii = 9, [0, 170, 430, 820, 2600]
    angs = sorted(rng.uniform(0, 2 * math.pi) for _ in range(K))
    jit = [[rng.uniform(-0.12, 0.12) for _ in radii] for _ in range(K)]

    def P(i, j):
        ang = angs[i % K] + jit[i % K][j] + (2 * math.pi if i >= K else 0)
        r = radii[j]
        return (cx + r * math.cos(ang), cy + r * math.sin(ang))

    polys = [[P(i, j), P(i, j + 1), P(i + 1, j + 1), P(i + 1, j)]
             for i in range(K) for j in range(len(radii) - 1)]

    def chroma(img: Image.Image, dx: int) -> Image.Image:
        if dx == 0:
            return img
        arr = np.asarray(img).copy()
        arr[:, :, 0] = np.roll(arr[:, :, 0], dx, axis=1)
        arr[:, :, 2] = np.roll(arr[:, :, 2], -dx, axis=1)
        return Image.fromarray(arr)

    def zoom(img: Image.Image, z: float, ox: float = 0, oy: float = 0) -> Image.Image:
        bw, bh = W / z, H / z
        x0, y0 = (W - bw) / 2 + ox, (H - bh) / 2 + oy
        return img.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))

    def cracks(img: Image.Image, prog: float) -> Image.Image:
        img = img.copy()
        d = ImageDraw.Draw(img)
        lim = prog * 1100
        for poly in polys:
            for k in range(4):
                p0, p1 = poly[k], poly[(k + 1) % 4]
                r0 = math.hypot(p0[0] - cx, p0[1] - cy)
                r1 = math.hypot(p1[0] - cx, p1[1] - cy)
                if max(r0, r1) <= lim + 1:
                    d.line([(p0[0] + 2, p0[1] + 2), (p1[0] + 2, p1[1] + 2)], fill=(20, 20, 20), width=4)
                    d.line([p0, p1], fill=(245, 245, 250), width=3)
        return img

    # cacos: recortes do quadro rachado
    base = cracks(ImageEnhance.Color(zoom(a, 1.08)).enhance(0.25), 1.0)
    pieces = []
    for poly in polys:
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).polygon(poly, fill=255)
        bbox = m.getbbox()
        if not bbox:
            continue
        pc = base.crop(bbox).convert("RGBA")
        pc.putalpha(m.crop(bbox))
        mx, my = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        ang = math.atan2(my - cy, mx - cx)
        sp = rng.uniform(500, 1300)
        pieces.append({"img": pc, "x": bbox[0], "y": bbox[1], "vx": math.cos(ang) * sp,
                       "vy": math.sin(ang) * sp - rng.uniform(150, 450), "w": rng.uniform(-260, 260)})

    vf = []
    if int(cfg.get("video.grain", 0)):
        vf.append(f"noise=alls={int(cfg.get('video.grain'))}:allf=t")
    if cfg.get("video.vignette", True):
        vf.append("vignette=angle=PI/5.5")
    vf.append("format=yuv420p")
    cmd = [ffmpeg.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
           "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-vf", ",".join(vf),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    try:
        for f in range(n):
            t = f / fps
            if style != "shatter":
                fr = _shock_alt(style, a, b, t, dur, f, W, H, rng, zoom, chroma)
            elif t < tA:                                 # congela + racha
                q = t / tA
                e = 1 - (1 - q) ** 3
                fr = ImageEnhance.Color(zoom(a, 1.0 + 0.08 * e, rng.uniform(-6, 6) * q, rng.uniform(-6, 6) * q)).enhance(1 - 0.75 * e)
                fr = chroma(cracks(fr, e), int(14 * e))
            elif t < tB:                                 # estilhaca
                u = t - tA
                fr = black.copy()
                for pc in pieces:
                    x = pc["x"] + pc["vx"] * u
                    y = pc["y"] + pc["vy"] * u + 0.5 * 5200 * u * u
                    im = pc["img"].rotate(pc["w"] * u, resample=Image.BICUBIC, expand=True)
                    fr.paste(im, (int(x), int(y)), im)
                fade = max(0.0, 1 - u / (tB - tA) * 0.9)
                fr = ImageEnhance.Brightness(fr).enhance(fade)
                if u < 2 / fps:                          # flash do impacto
                    fr = Image.blend(fr, Image.new("RGB", (W, H), (255, 255, 255)), 0.7)
            elif t < tC:                                 # sinal perdido
                arr = np.zeros((H, W, 3), np.uint8)
                for _ in range(10):
                    y0 = rng.randrange(0, H - 6)
                    arr[y0:y0 + rng.randrange(2, 6)] = rng.randrange(60, 200)
                noise = (np.random.default_rng(f).random((H // 4, W // 4)) * 70).astype(np.uint8)
                arr = np.maximum(arr, np.kron(noise, np.ones((4, 4), np.uint8))[:H, :W, None])
                fr = Image.fromarray(arr)
            else:                                        # a realidade bate na tela
                u = (t - tC) / max(0.001, dur - tC)
                k = math.exp(-5.5 * u)
                fr = zoom(b, 1.0 + 0.12 * k, rng.uniform(-28, 28) * k, rng.uniform(-28, 28) * k)
                fr = ImageEnhance.Brightness(fr).enhance(1 + 0.9 * k)
                fr = ImageEnhance.Color(fr).enhance(1 - 0.6 * k)
                fr = chroma(fr, int(18 * k))
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"shock {out.name}: {err[-1500:]}")
    return out


# --------------------------------------------------------------------------
# 3) audio: voz + trilha por humor + efeitos
# --------------------------------------------------------------------------
SFX_EXPR = {
    # batida dupla de coracao (tum-tum), grave
    "heartbeat": ("0.9*sin(2*PI*52*t)*(exp(-28*mod(t,0.92))+0.7*exp(-28*(mod(t,0.92)-0.24))*gte(mod(t,0.92),0.24))",
                  "lowpass=f=160,volume=2.2"),
    # salto no piso de madeira
    "heels": ("(random(0)*0.6+0.5*sin(2*PI*1900*t))*exp(-55*mod(t,0.58))",
              "highpass=f=700,lowpass=f=6000,aecho=0.8:0.5:60:0.25,volume=0.55"),
    # despertador digital
    "alarm": ("0.32*sin(2*PI*1760*t)*lt(mod(t,0.24),0.11)*lt(mod(t,1.0),0.62)", "volume=0.9"),
    # estatica do corte
    "glitch": ("random(0)*exp(-7*t)", "bandpass=f=2500:w=3000,volume=0.6"),
}


def _sfx_file(name: str, dur: float, work: Path) -> Path:
    if name == "whoosh":
        return ROOT / "assets" / "sfx" / "whoosh.mp3"
    expr, af = SFX_EXPR[name]
    out = work / "sfx" / f"{name}_{dur:.2f}.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        _run_ff(["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={dur:.2f}",
                 "-af", f"{af},afade=t=out:st={max(0, dur - 0.4):.2f}:d=0.4", str(out)])
    return out


def _gain_to(path: Path, target_lufs: float) -> float:
    """dB para levar o arquivo ao nivel alvo (cache por arquivo)."""
    meta = path.with_suffix(".lufs")
    if meta.exists():
        cur = float(meta.read_text())
    else:
        cur = tts._lufs(path)
        cur = -30.0 if cur is None or cur < -70 else cur
        meta.write_text(str(cur))
    return max(-30.0, min(30.0, target_lufs - cur))


def _ambience_spans(p: dict, bible: dict) -> list[dict]:
    """Ambiente por cena (do lugar na biblia, ou `ambience:` da cena).
    Cenas seguidas com o mesmo ambiente viram um trecho continuo."""
    spans: list[dict] = []
    for it in p["shots"]:
        sh = it["shot"]
        if sh.get("card"):
            prompt = sh.get("ambience")
        elif "ambience" in sh:
            prompt = sh["ambience"]
        else:
            prompt = ((bible.get("locations") or {}).get(sh.get("location")) or {}).get("ambience")
        if not prompt or str(prompt).lower() == "none":
            continue
        vol = float(sh.get("ambience_db", 0.0))
        end = it["start"] + it["dur"]
        if spans and spans[-1]["prompt"] == prompt and abs(spans[-1]["end"] - it["start"]) < 0.05:
            spans[-1]["end"] = end
            spans[-1]["hard_out"] = it["c_out"] < 0.4
        else:
            spans.append({"prompt": prompt, "start": it["start"], "end": end, "db": vol,
                          "hard_in": it["c_in"] < 0.4, "hard_out": it["c_out"] < 0.4,
                          "c_out": it["c_out"]})
    return spans


def build_audio(p: dict, cfg: Config, work: Path) -> tuple[Path, list[dict]]:
    total = p["total"]
    inputs: list[list[str]] = []
    voice_lbl, music_lbl, sfx_lbl, filters = [], [], [], []
    timeline = []

    def add_input(args):
        inputs.append(args)
        return len(inputs) - 1

    # voz
    for it in p["shots"]:
        for ln in it["lines"]:
            L = ln["line"]
            t0 = it["start"] + ln["offset"]
            k = add_input(["-i", str(L.audio)])
            ms = int(t0 * 1000)
            filters.append(f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{k}]")
            voice_lbl.append(f"[v{k}]")
            timeline.append({"who": L.who, "tr": L.tr, "card": bool(it["shot"].get("card")),
                             "words": [tts.Word(w.text, w.start + t0, w.end + t0) for w in L.words]})

    # trilha: cada cue vale ate o proximo
    tracks = cfg.get("music.tracks", {})
    gvol = float(cfg.get("music.volume", 0.16))
    cues = [(it["start"], it["shot"].get("music"), it["shot"].get("transition"))
            for it in p["shots"] if it["shot"].get("music")]
    for i, (st, name, _tr) in enumerate(cues):
        end = cues[i + 1][0] if i + 1 < len(cues) else total
        hard = i + 1 < len(cues) and cues[i + 1][2] in ("flash", "cut")
        if name == "none" or name not in tracks or end - st < 0.5:
            continue
        tr = tracks[name]
        ln = end - st + (0.0 if hard else 0.8)
        k = add_input(["-stream_loop", "-1", "-i", str(ROOT / tr["file"])])
        fo = 0.12 if hard else 1.4
        flt = (tr.get("filter") or "").strip()
        ms = int(st * 1000)
        filters.append(
            f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{ln:.3f},asetpts=PTS-STARTPTS,"
            + (flt + "," if flt else "")
            + f"volume={gvol * float(tr.get('volume', 1.0)):.3f},afade=t=in:d=1.2,"
            f"afade=t=out:st={max(0, ln - fo):.3f}:d={fo},adelay={ms}|{ms}[m{k}]")
        music_lbl.append(f"[m{k}]")

    # ambiente (som do lugar): canal proprio, abaixa um pouco sob a voz
    amb_lbl = []
    amb_lufs = float(cfg.get("ambience.lufs", -33))
    for sp in _ambience_spans(p, bible()):
        try:
            f = elevenlabs.sound(sp["prompt"], duration=float(cfg.get("ambience.loop_seconds", 12)), loop=True)
        except (elevenlabs.Unavailable, elevenlabs.OverCap) as exc:
            print(f"  !! ambiente sem som ({exc})")
            continue
        g = _gain_to(f, amb_lufs) + sp["db"]
        st = max(0.0, sp["start"] - (0.05 if sp["hard_in"] else 0.6))
        ln = min(total, sp["end"] + (0.05 if sp["hard_out"] else sp["c_out"])) - st
        fi = 0.08 if sp["hard_in"] else 1.2
        fo = 0.08 if sp["hard_out"] else 1.0
        k = add_input(["-stream_loop", "-1", "-i", str(f)])
        ms = int(st * 1000)
        filters.append(f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{ln:.3f},asetpts=PTS-STARTPTS,"
                       f"volume={g:.2f}dB,afade=t=in:d={fi},afade=t=out:st={max(0, ln - fo):.3f}:d={fo},"
                       f"adelay={ms}|{ms}[a{k}]")
        amb_lbl.append(f"[a{k}]")

    # efeitos
    sfx_lufs = float(cfg.get("sfx.lufs", -24))
    for it in p["shots"]:
        for spec in it["shot"].get("sfx", []) or []:
            S = it["start"]
            name = spec if isinstance(spec, str) else spec.get("name", "gen")
            if isinstance(spec, dict) and "after_line" in spec:
                ln = it["lines"][int(spec["after_line"])]
                S = it["start"] + ln["offset"] + ln["line"].duration + 0.15 - 0.1
            elif isinstance(spec, dict) and "line" in spec:
                ln = it["lines"][int(spec["line"])]
                S = it["start"] + ln["offset"]
            elif isinstance(spec, dict) and "word" in spec:
                # entra quando a voz diz essa palavra (1a ocorrencia na cena)
                target = tts._norm(str(spec["word"]))
                hit = next(((ln, w) for ln in it["lines"] for w in ln["line"].words
                            if tts._norm(w.text) == target), None)
                if hit is None:
                    print(f"  !! {it['shot']['id']}: palavra '{spec['word']}' nao encontrada para o efeito")
                else:
                    S = it["start"] + hit[0]["offset"] + hit[1].start
            if isinstance(spec, dict) and "at" in spec:
                S = S + float(spec["at"])
            if isinstance(spec, dict) and spec.get("gen"):
                # efeito gerado (ElevenLabs Sound Effects), em cache em assets/sfx/gen
                try:
                    f = elevenlabs.sound(spec["gen"], duration=spec.get("dur"))
                except (elevenlabs.Unavailable, elevenlabs.OverCap) as exc:
                    print(f"  !! efeito sem som ({exc})")
                    continue
                g = _gain_to(f, sfx_lufs) + float(spec.get("db", 0.0))
                k = add_input(["-i", str(f)])
                ms = int(max(0, S) * 1000)
                filters.append(f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo,volume={g:.2f}dB,"
                               f"afade=t=out:st={max(0.0, float(spec.get('dur') or 30) - 0.3):.2f}:d=0.3,"
                               f"adelay={ms}|{ms}[s{k}]")
                sfx_lbl.append(f"[s{k}]")
                continue
            if name == "whoosh":
                at, d = S - 0.25, None
            elif name == "glitch":
                at, d = S - 0.05, 0.45
                kw = add_input(["-i", str(_sfx_file("whoosh", 0, work))])
                ms = int(max(0, S - 0.3) * 1000)
                filters.append(f"[{kw}:a]aresample=44100,aformat=channel_layouts=stereo,volume=1.3,adelay={ms}|{ms}[s{kw}]")
                sfx_lbl.append(f"[s{kw}]")
            elif name == "heels":
                at, d = S + 0.2, 2.4
            elif name == "heartbeat":
                at, d = S + 0.3, max(1.0, it["dur"] - 0.5)
            elif name == "alarm":
                at, d = S + 0.1, 2.6
            else:
                continue
            k = add_input(["-i", str(_sfx_file(name, d or 0, work))])
            ms = int(max(0, at) * 1000)
            filters.append(f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={ms}|{ms}[s{k}]")
            sfx_lbl.append(f"[s{k}]")

    mix = []
    filters.append("".join(voice_lbl) + f"amix=inputs={len(voice_lbl)}:normalize=0:dropout_transition=0,"
                   f"apad=whole_dur={total:.3f}[voice]")
    filters.append("[voice]asplit=3[vo][vsc][vsa]")
    mix.append("[vo]")
    if amb_lbl:
        filters.append("".join(amb_lbl) + f"amix=inputs={len(amb_lbl)}:normalize=0:dropout_transition=0[amb]")
        filters.append("[amb][vsa]sidechaincompress=threshold=0.03:ratio=2.5:attack=60:release=700[ambd]")
        mix.append("[ambd]")
    else:
        filters.append("[vsa]anullsink")
    if music_lbl:
        filters.append("".join(music_lbl) + f"amix=inputs={len(music_lbl)}:normalize=0:dropout_transition=0[mus]")
        if cfg.get("music.duck", True):
            filters.append("[mus][vsc]sidechaincompress=threshold=0.025:ratio=6:attack=30:release=500[musd]")
        else:
            filters.append("[vsc]anullsink;[mus]anull[musd]")
        mix.append("[musd]")
    else:
        filters.append("[vsc]anullsink")
    if sfx_lbl:
        filters.append("".join(sfx_lbl) + f"amix=inputs={len(sfx_lbl)}:normalize=0:dropout_transition=0[sfx]")
        mix.append("[sfx]")
    lufs = float(cfg.get("music.loudness_lufs", -14))
    filters.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:dropout_transition=0,"
                   f"atrim=0:{total:.3f},loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=44100,alimiter=limit=0.84:level=false[aout]")
    script = work / "audio_filter.txt"
    script.write_text(";\n".join(filters), encoding="utf-8")
    out = work / "mix.wav"
    args = [a for inp in inputs for a in inp]
    _run_ff(args + ["-filter_complex_script", str(script), "-map", "[aout]", "-ac", "2", str(out)])
    return out, timeline


# --------------------------------------------------------------------------
# 4) episodio completo
# --------------------------------------------------------------------------
def build(ep_id: str, *, only_audio: bool = False, retake: set | None = None) -> dict:
    cfg = load_config()
    b = bible()
    W, H = int(cfg.get("video.width")), int(cfg.get("video.height"))
    out_dir = ROOT / "output" / ep_id
    work = out_dir / "_work"
    clips_dir = work / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    frames = out_dir / "frames"

    # episodio NOVO (nenhuma fala em cache): consulta o saldo ANTES de chamar a ElevenLabs
    if cfg.get("tts.provider", "elevenlabs") == "elevenlabs" and not list((work / "tts").glob("11_*.mp3")):
        from . import elevenlabs
        ok, msg = elevenlabs.preflight(elevenlabs.estimate(episode(ep_id)), ep_id)
        if not ok:
            raise SystemExit(f"sem credito de voz suficiente — nada foi gasto. {msg}")
    print("[1/5] narracao e linha do tempo")
    p = plan(ep_id, cfg, retake)
    ep = p["ep"]
    print(f"      duracao: {p['total']:.1f}s em {len(p['shots'])} cenas")
    if p["total"] > float(cfg.get("video.max_seconds", 179)):
        print(f"      ATENCAO: passa de {cfg.get('video.max_seconds')}s (limite do Shorts)")

    print("[2/5] audio (voz + trilha + efeitos)")
    mix, timeline = build_audio(p, cfg, work)

    print("[3/5] legendas")
    ass = subs.build_ass(timeline, cfg, work / "captions.ass", W, H)
    srt = subs.build_srt(timeline, out_dir / f"{ep_id}.srt")
    audiobook = out_dir / f"{ep_id}_audiobook.mp3"
    _run_ff(["-i", str(mix), "-c:a", "libmp3lame", "-b:a", "192k",
             "-metadata", f"title=Ep. {ep['number']} — {ep['title']}",
             "-metadata", f"album={b['series']['title']}", str(audiobook)])
    if only_audio:
        return {"audio": mix}

    print("[4/5] clipes (camera + cor)")
    clips, lens = [], []
    for it in p["shots"]:
        sh = it["shot"]
        L = it["dur"] + it["c_out"]
        out = clips_dir / f"{sh['id']}.mp4"
        if sh.get("card") == "shock":
            i = p["shots"].index(it)
            pa, pb = p["shots"][i - 1]["shot"], p["shots"][i + 1]["shot"]
            lk = lambda s: s.get("look") or b["locations"][s["location"]]["look"]  # noqa: E731
            render_shock(frames / f"{pa['id']}.png", frames / f"{pb['id']}.png", L, out, cfg,
                         motion_from=pa.get("motion", "push_in"), motion_to=pb.get("motion", "push_in"),
                         look_from=lk(pa), look_to=lk(pb), style=sh.get("style", "shatter"))
        elif sh.get("card"):
            texts = dict(ep.get("cards", {}).get(sh["card"], {}))
            img = cards.card(frames / f"{sh['bg']}.png", sh["card"], texts, W, H,
                             work / f"card_{sh['id']}.jpg", series=b["series"]["title"])
            render_clip(img, L, "push_in", "", out, cfg)
        else:
            src = frames / f"{sh['id']}.png"
            if not src.exists():
                raise FileNotFoundError(f"imagem da cena ausente: {src} (rode `python main.py frames {ep_id}`)")
            look = sh.get("look") or b["locations"][sh["location"]]["look"]
            render_clip(src, L, sh.get("motion", "push_in"), look, out, cfg,
                        glitch=any((x if isinstance(x, str) else x.get("name")) == "glitch"
                                   for x in (sh.get("sfx") or [])))
        print(f"      {sh['id']}  {L:5.2f}s")
        clips.append(out)
        lens.append(L)

    print("[5/5] montagem final + legendas queimadas")
    filters, prev = [], "[0:v]"
    for i in range(1, len(clips)):
        it = p["shots"][i]
        name = XFADE.get(it["shot"].get("transition", "dissolve"), "fade")
        lbl = f"[x{i}]"
        filters.append(f"{prev}[{i}:v]xfade=transition={name}:duration={it['c_in']:.3f}:"
                       f"offset={it['start']:.3f}{lbl}")
        prev = lbl
    rel_ass = ass.relative_to(ROOT).as_posix()
    rel_fonts = FONTS.relative_to(ROOT).as_posix()
    filters.append(f"{prev}subtitles={rel_ass}:fontsdir={rel_fonts},format=yuv420p[vout]")
    script = work / "video_filter.txt"
    script.write_text(";\n".join(filters), encoding="utf-8")
    final = out_dir / f"{ep_id}.mp4"
    args = []
    for c in clips:
        args += ["-i", str(c)]
    args += ["-i", str(mix)]
    _run_ff(args + ["-filter_complex_script", str(script), "-map", "[vout]", "-map", f"{len(clips)}:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{p['total']:.3f}",
                    "-movflags", "+faststart", str(final)], cwd=ROOT)

    # metadados + status de aprovacao
    meta = {"episode": ep_id, "duration": round(p["total"], 2), "video": final.name,
            "srt": srt.name, "audiobook": audiobook.name, "publish": ep.get("publish", {}),
            "shots": [{"id": it["shot"]["id"], "start": round(it["start"], 2), "dur": round(it["dur"], 2)}
                      for it in p["shots"]]}
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    st = out_dir / "status.json"
    status = json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}
    status.update({"approved": False, "published": status.get("published", {})})
    st.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK -> {final}  ({p['total']:.1f}s)")
    return meta
