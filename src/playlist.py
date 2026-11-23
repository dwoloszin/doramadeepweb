"""Playlist do YouTube com TODOS os episodios em ordem (para quem chega agora maratonar).

  python main.py playlist          # cria (se preciso) e adiciona os episodios que faltam

* So episodios (nao os Shorts de teaser), na ordem ep01, ep02, ...
* Episodio agendado (privado ate domingo) pode entrar ja: o YouTube so mostra quando abrir.
* O id da playlist fica em output/youtube_playlist.json (versionado, nao e segredo).
* O autopilot chama sync() depois de cada envio de episodio.
"""
from __future__ import annotations

import json
import re

from .config import ROOT, Config

STATE = ROOT / "output" / "youtube_playlist.json"
TITLE = "Dorama da Deep Web — Todos os Episódios em Ordem"
DESCRIPTION = (
    "Chegou agora? Comece por aqui! 💚\n"
    "Todos os episódios da história do Davi, do primeiro ao último, na ordem certa.\n"
    "Baseado em fatos reais — 80% verdade, 20% imaginação.\n"
    "Episódio novo todo domingo, 12h."
)


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _episodes() -> list[tuple[int, str, str]]:
    """[(numero, epNN, video_id)] dos episodios ja enviados ao YouTube, em ordem."""
    out = []
    for d in (ROOT / "output").glob("ep[0-9]*"):
        m = re.fullmatch(r"ep(\d+)", d.name)
        st = d / "status.json"
        if not m or not st.exists():
            continue
        vid = (json.loads(st.read_text(encoding="utf-8")).get("published") or {}).get("youtube")
        if vid:
            out.append((int(m.group(1)), d.name, vid))
    return sorted(out)


def ensure(svc) -> str:
    st = _state()
    pid = st.get("id")
    if pid:
        r = svc.playlists().list(part="id", id=pid).execute()
        if r.get("items"):
            return pid
    body = {"snippet": {"title": TITLE, "description": DESCRIPTION, "defaultLanguage": "pt-BR"},
            "status": {"privacyStatus": "public"}}
    pid = svc.playlists().insert(part="snippet,status", body=body).execute()["id"]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"id": pid, "title": TITLE}, indent=2), encoding="utf-8")
    print(f"  [playlist] criada: https://www.youtube.com/playlist?list={pid}")
    return pid


def sync(cfg: Config | None = None, dry: bool = False) -> str | None:
    from . import publish
    eps = _episodes()
    if dry:
        print("  [playlist] (dry) episodios:", ", ".join(e for _, e, _ in eps))
        return None
    svc = publish._yt_service()
    pid = ensure(svc)
    have, tok = [], None
    while True:
        try:
            r = svc.playlistItems().list(part="snippet", playlistId=pid, maxResults=50, pageToken=tok).execute()
        except Exception as exc:  # noqa: BLE001  playlist recem-criada/vazia as vezes responde 404
            if "playlistNotFound" not in str(exc):
                raise
            break
        have += [i["snippet"]["resourceId"]["videoId"] for i in r.get("items", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break
    for n, ep, vid in eps:
        if vid in have:
            continue
        # posicao = quantos episodios ANTERIORES ja estao na playlist -> fica sempre em ordem
        pos = sum(1 for m, _, v in eps if m < n and v in have)
        body = {"snippet": {"playlistId": pid, "position": pos,
                            "resourceId": {"kind": "youtube#video", "videoId": vid}}}
        try:
            svc.playlistItems().insert(part="snippet", body=body).execute()
        except Exception:  # noqa: BLE001  (playlist sem ordem manual nao aceita position)
            body["snippet"].pop("position")
            svc.playlistItems().insert(part="snippet", body=body).execute()
        have.append(vid)
        print(f"  [playlist] + {ep}")
    return pid
