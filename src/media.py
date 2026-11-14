"""Midia pesada dos episodios nas GitHub Releases (o git so guarda texto e caches pequenos).

Cada episodio tem uma release `media-epNN` com:
  epNN.mp4, epNN_audiobook.mp3, frames.zip, carousel.zip, teaser.zip
(o GitHub recusa arquivo > 100 MB no repositorio; release aceita ate 2 GB por arquivo).

Usa o `gh` (GitHub CLI): local, com o seu login; no Actions, com GH_TOKEN.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .config import ROOT

DIRS = ("frames", "carousel", "teaser")


def tag(ep_id: str) -> str:
    return f"media-{ep_id}"


def _gh(*args: str, check: bool = True, timeout: int = 3600) -> subprocess.CompletedProcess:
    r = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {r.stderr.strip()[-400:]}")
    return r


def exists(ep_id: str) -> bool:
    return _gh("release", "view", tag(ep_id), check=False).returncode == 0


def has_video(ep_id: str) -> bool:
    """A release ja tem o video (e nao so frames)?"""
    r = _gh("release", "view", tag(ep_id), "--json", "assets", "-q", ".assets[].name", check=False)
    return r.returncode == 0 and f"{ep_id}.mp4" in r.stdout.split()


def rendered(ep_id: str) -> bool:
    """Ja foi renderizado (metadata.json no git, video local ou release)? Nunca re-renderiza
    sozinho um episodio que ja existe: refazer e sempre decisao manual."""
    out = ROOT / "output" / ep_id
    return (out / "metadata.json").exists() or (out / f"{ep_id}.mp4").exists() or has_video(ep_id)


def push(ep_id: str, light: bool = False) -> None:
    """Sobe (ou atualiza) a midia do episodio na release. light=True: so frames/carrossel/teasers (sem video)."""
    out = ROOT / "output" / ep_id
    video = out / f"{ep_id}.mp4"
    if not video.exists() and not light:
        raise FileNotFoundError(f"{video} nao existe (renderize antes)")
    tmp = Path(tempfile.mkdtemp(prefix="media_"))
    try:
        files = [] if light else [video]
        audio = out / f"{ep_id}_audiobook.mp3"
        if audio.exists() and not light:
            files.append(audio)
        for d in DIRS:
            src = out / d
            if src.exists() and any(src.iterdir()):
                z = tmp / f"{d}.zip"
                with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in sorted(src.rglob("*")):
                        if f.is_file():
                            zf.write(f, f.relative_to(src).as_posix())
                files.append(z)
        if not exists(ep_id):
            _gh("release", "create", tag(ep_id), "--title", f"Mídia {ep_id}",
                "--notes", f"Vídeo, áudio, frames, carrossel e teasers do {ep_id} (gerado pelo pipeline).")
        _gh("release", "upload", tag(ep_id), *[str(f) for f in files], "--clobber")
        print(f"  [media] {ep_id}: {len(files)} arquivo(s) na release {tag(ep_id)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pull(ep_id: str, what: tuple[str, ...] = ("video", "carousel", "teaser")) -> None:
    """Baixa da release o que faltar em output/epNN (video, frames, carousel, teaser)."""
    out = ROOT / "output" / ep_id
    out.mkdir(parents=True, exist_ok=True)
    pats = []
    if "video" in what and not (out / f"{ep_id}.mp4").exists():
        pats.append(f"{ep_id}.mp4")
    for d in DIRS:
        if d in what and not ((out / d).exists() and any((out / d).iterdir())):
            pats.append(f"{d}.zip")
    if not pats or not exists(ep_id):
        return
    tmp = Path(tempfile.mkdtemp(prefix="pull_"))
    try:
        args = ["release", "download", tag(ep_id), "--dir", str(tmp)]
        for p in pats:
            args += ["--pattern", p]
        _gh(*args)
        for f in tmp.iterdir():
            if f.suffix == ".zip":
                with zipfile.ZipFile(f) as zf:
                    zf.extractall(out / f.stem)
            else:
                shutil.move(str(f), out / f.name)
        print(f"  [media] {ep_id}: baixado {', '.join(pats)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
