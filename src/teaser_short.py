"""Teaser em VIDEO (YouTube Shorts) — a imagem do teaser com zoom lento + voz do narrador
lendo o gancho + trilha de suspense. ~8-10 s, vertical 1080x1920.

Por que: post de comunidade (foto) no YouTube nao tem API; o Short mantem a constancia no canal
(ter/qui/sab teaser + domingo episodio), igual ao Instagram e ao TikTok.

Arquivo: output/epNN/teaser/<id>_short.mp4 (vai junto no teaser.zip da release).
Fala: campo `voice:` no item do teaser (opcional); sem ele, monta a partir do titulo.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import elevenlabs, ffmpeg, render, tts
from .config import ROOT, load_config
from .story import episode

STING = "Short suspenseful cinematic riser ending in a deep mysterious impact hit"
BED = "Soft mysterious suspense music bed with a slow ticking pulse and low strings"


def _clean(s: str) -> str:
    return re.sub(r"\*\*", "", s or "").strip()


def voice_text(ep: dict, t: dict) -> str:
    if t.get("voice"):
        return t["voice"]
    if t.get("style") == "poster":
        return (f"[Brazilian accent] [mysterious] Próximo episódio: {_clean(t.get('title') or ep['title'])}. "
                f"[excited] Domingo, meio-dia, aqui no canal!")
    return (f"[Brazilian accent] [suspenseful] Alerta de spoiler! [mysterious] {_clean(t.get('title'))} "
            f"[excited] Domingo, meio-dia, episódio novo!")


def yt_publish(ep: dict, t: dict) -> dict:
    """Titulo/descricao/tags do Short de teaser."""
    n = ep["number"]
    if t.get("style") == "poster":
        title = f"🎬 Próximo episódio — Ep. {n}: {_clean(t.get('title') or ep['title'])}"
    else:
        title = f"🚨 Alerta de spoiler — Ep. {n}: {_clean(t.get('title'))}"
    if len(title) > 90:
        title = title[:89].rstrip() + "…"
    title += " #shorts"
    desc = (t.get("caption") or "").strip()
    desc += ("\n\n▶ O episódio completo estreia no domingo, 12h, aqui no canal."
             "\n📸 Instagram: https://www.instagram.com/doramadadeepweb/ · 🎵 TikTok: https://www.tiktok.com/@doramamagico")
    tags = list((ep.get("publish") or {}).get("tags", []))[:15] + ["spoiler", "teaser", "proximo episodio"]
    return {"title": title, "description": desc, "tags": tags}


def build(ep_id: str, tid: str, *, force: bool = False) -> Path:
    cfg = load_config()
    ep = episode(ep_id)
    t = next(x for x in (ep.get("teaser") or []) if x["id"] == tid)
    tdir = ROOT / "output" / ep_id / "teaser"
    out = tdir / f"{tid}_short.mp4"
    img = tdir / f"{tid}_story.png"
    if not img.exists():
        raise FileNotFoundError(f"{img} nao existe (rode `python main.py teaser {ep_id}`)")
    text = voice_text(ep, t)
    key = hashlib.sha1(f"{text}|{img.stat().st_size}".encode()).hexdigest()[:10]
    stamp = tdir / f"{tid}_short.key"
    if out.exists() and not force and stamp.exists() and stamp.read_text().strip() == key:
        return out

    v = dict(cfg.get("voices")["narrador"])
    cache = tdir / "_voz"
    cache.mkdir(parents=True, exist_ok=True)
    raw = cache / f"{tid}_{key}.mp3"
    if not raw.exists():
        elevenlabs.synthesize(text, raw, v, str(cfg.get("tts.model", "eleven_v3")))
    voice = tts._apply_fx(raw, v.get("fx", ""), tempo=float(v.get("tempo", 1.0)),
                          level=float(v.get("level_lufs", -18)))
    vdur = ffmpeg.probe_duration(voice)
    dur = max(7.0, vdur + 1.8)
    tmp = Path(tempfile.mkdtemp(prefix="tshort_"))
    try:
        clip = render.render_clip(img, dur, "push_in", "", tmp / "v.mp4", cfg)
        sting = elevenlabs.sound(STING, duration=3)
        bed = elevenlabs.sound(BED, duration=min(22.0, dur + 1))
        fc = ("[1:a]adelay=700|700,volume=1.0[vo];"
              "[2:a]volume=0.55[st];"
              f"[3:a]volume=0.22,atrim=0:{dur:.2f},afade=t=out:st={dur - 1.2:.2f}:d=1.2[bd];"
              "[vo][st][bd]amix=inputs=3:normalize=0:duration=longest,"
              f"atrim=0:{dur:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        subprocess.run([ffmpeg.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(clip), "-i", str(voice),
                        "-i", str(sting), "-i", str(bed), "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
                        "-movflags", "+faststart", str(out)], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stamp.write_text(key)
    print(f"  [teaser-short] {ep_id} {tid} -> {out.name} ({dur:.1f}s)")
    return out
