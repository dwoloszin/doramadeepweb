"""Publicacao no YouTube (Shorts) e Instagram (Reel + carrossel).

TRAVADO por padrao. Para sair qualquer coisa, as tres coisas precisam valer:
  1. config.yaml -> youtube.enabled / instagram.enabled = true
  2. episodio aprovado:  python main.py approve ep01
  3. comando explicito:  python main.py publish ep01 --youtube --instagram --yes

Sem --yes o comando so mostra o que SERIA publicado (dry run).

Adaptado do ubt-bemnamosca (mesmo fluxo OAuth do YouTube e mesma hospedagem
temporaria no GitHub para o Instagram buscar o arquivo).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from .config import ROOT, Config

IG_API = "https://graph.instagram.com/v21.0"       # token IGAA... (login do Instagram)
FB_API = "https://graph.facebook.com/v21.0"        # token EAA... (Unified login / usuario do sistema)
MEDIA_REPO = "doramadeepweb-media"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


# --------------------------------------------------------------------------
# status / aprovacao
# --------------------------------------------------------------------------
def status_path(ep_id: str) -> Path:
    return ROOT / "output" / ep_id / "status.json"


def load_status(ep_id: str) -> dict:
    p = status_path(ep_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_status(ep_id: str, st: dict) -> None:
    status_path(ep_id).write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def approve(ep_id: str, value: bool = True) -> None:
    st = load_status(ep_id)
    st["approved"] = value
    st["approved_at"] = time.strftime("%Y-%m-%d %H:%M") if value else None
    save_status(ep_id, st)
    print(f"{ep_id}: {'APROVADO' if value else 'aprovacao removida'}")


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------
def _yt_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    token, secret = ROOT / "token.json", ROOT / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret.exists():
                raise FileNotFoundError("client_secret.json ausente na raiz (OAuth Desktop app do Google Cloud)")
            creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def next_slot(cfg: Config):
    """Proximo horario de youtube.schedule (ex.: 12:00, 18:00 em Sao Paulo), com folga minima."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    slots = cfg.get("youtube.schedule", []) or []
    if not slots:
        return None
    tz = ZoneInfo(str(cfg.get("youtube.timezone", "America/Sao_Paulo")))
    now = dt.datetime.now(tz) + dt.timedelta(minutes=float(cfg.get("youtube.min_lead_minutes", 30)))
    for day in range(0, 8):
        d = (now + dt.timedelta(days=day)).date()
        for s in sorted(slots):
            h, m = map(int, str(s).split(":"))
            t = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
            if t > now:
                return t
    return None


def youtube_upload(cfg: Config, video: Path, meta: dict, srt: Path | None, when=None) -> str:
    """when = datetime da estreia (agenda); None = proximo horario de youtube.schedule."""
    from googleapiclient.http import MediaFileUpload
    svc = _yt_service()
    pub = meta["publish"]
    body = {
        "snippet": {"title": pub["title"][:100], "description": pub.get("description", "")[:4900],
                    "tags": pub.get("tags", []), "categoryId": str(cfg.get("youtube.category_id", "24")),
                    "defaultLanguage": "pt-BR", "defaultAudioLanguage": "pt-BR"},
        "status": {"privacyStatus": cfg.get("youtube.privacy", "private"),
                   "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(cfg.get("youtube.synthetic_media", True))},
    }
    when = when or next_slot(cfg)
    if when:  # agendado: fica privado ate o horario e o YouTube abre sozinho
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = when.astimezone(__import__("datetime").timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
        print(f"  [youtube] agendado para {when:%d/%m %H:%M} (Brasilia)")
    req = svc.videos().insert(part="snippet,status", body=body,
                              media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True,
                                                         mimetype="video/mp4"))
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print(f"  [youtube] {int(st.progress() * 100)}%")
    vid = resp["id"]
    print(f"  [youtube] enviado: https://youtu.be/{vid}")
    if srt and srt.exists():
        try:
            svc.captions().insert(part="snippet", body={"snippet": {
                "videoId": vid, "language": "pt-BR", "name": "Português", "isDraft": False}},
                media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
            print("  [youtube] legenda .srt anexada")
        except Exception as exc:  # noqa: BLE001
            print(f"  [youtube] legenda falhou: {exc}")
    return vid


# --------------------------------------------------------------------------
# Instagram (Reel + carrossel) — arquivo fica publico no GitHub so durante o envio
# --------------------------------------------------------------------------
IG_STATE = ROOT / "output" / "instagram_token.json"


def _ig_token() -> str:
    """Token atual: o renovado (output/instagram_token.json) ou a semente do .env.
    Renova sozinho a cada 30 dias (o token vive 60). Token novo no .env vence o salvo."""
    seed = (os.getenv("INSTAGRAM_ACCESS_TOKEN") or "").strip()
    tok, at = seed, 0.0
    if IG_STATE.exists():
        try:
            d = json.loads(IG_STATE.read_text(encoding="utf-8"))
            if d.get("seed") and seed and d["seed"] != seed:
                IG_STATE.unlink(missing_ok=True)
            else:
                tok, at = d.get("token") or seed, float(d.get("refreshed_at", 0))
        except Exception:  # noqa: BLE001
            pass
    if not tok:
        raise RuntimeError("INSTAGRAM_ACCESS_TOKEN ausente no .env (token do @doramadadeepweb)")
    if tok.startswith("IG") and time.time() - at > 30 * 86400:  # token EAA de sistema nao expira
        try:
            r = requests.get("https://graph.instagram.com/refresh_access_token",
                             params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30)
            if r.ok:
                tok = r.json()["access_token"]
                IG_STATE.parent.mkdir(parents=True, exist_ok=True)
                IG_STATE.write_text(json.dumps({"token": tok, "refreshed_at": time.time(), "seed": seed}),
                                    encoding="utf-8")
                print("  [instagram] token renovado (+60 dias)")
        except Exception as exc:  # noqa: BLE001
            print(f"  [instagram] renovacao falhou ({exc}); usando o token atual")
    return tok


def _ig() -> tuple[str, str, str]:
    """(api, id_da_conta, token). Aceita os dois tipos de token da Meta."""
    tok = _ig_token()
    if tok.startswith("IG"):
        return IG_API, "me", tok
    uid = (os.getenv("INSTAGRAM_USER_ID") or "").strip()
    if not uid:  # descobre pela pagina/portfolio ligados ao token
        r = requests.get(f"{FB_API}/me/accounts", params={
            "fields": "instagram_business_account{id,username}", "access_token": tok}, timeout=30)
        for pg in (r.json().get("data", []) if r.ok else []):
            if pg.get("instagram_business_account"):
                uid = pg["instagram_business_account"]["id"]
                break
    if not uid:
        raise RuntimeError("token do Facebook sem conta do Instagram achada: preencha INSTAGRAM_USER_ID no .env")
    return FB_API, uid, tok


def ig_account() -> dict:
    api, uid, tok = _ig()
    fields = "user_id,username,account_type" if uid == "me" else "id,username"
    r = requests.get(f"{api}/{uid}", params={"fields": fields, "access_token": tok}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Instagram recusou o token: {r.text[:300]}")
    d = r.json()
    d.setdefault("account_type", "via Facebook" if uid != "me" else "?")
    return d


def yt_channel() -> dict:
    items = _yt_service().channels().list(part="snippet", mine=True).execute().get("items", [])
    if not items:
        raise RuntimeError("essa conta Google nao tem canal do YouTube")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"],
            "handle": items[0]["snippet"].get("customUrl", "")}


def check(cfg: Config) -> None:
    """Confere as contas SEM publicar nada. 1a vez abre o navegador (YouTube)."""
    want_ch = str(cfg.get("youtube.channel_id", "") or "")
    try:
        ch = yt_channel()
        ok = "OK" if ch["id"] == want_ch else ("ANOTE em youtube.channel_id" if not want_ch else "CANAL ERRADO!")
        print(f"YouTube : {ch['title']} {ch['handle']} (id {ch['id']}) -> {ok}")
    except Exception as exc:  # noqa: BLE001
        print(f"YouTube : falhou — {exc}")
    want_ig = str(cfg.get("instagram.username", "") or "").lstrip("@").lower()
    try:
        acc = ig_account()
        ok = "OK" if acc.get("username", "").lower() == want_ig else "CONTA ERRADA!"
        print(f"Instagram: @{acc.get('username')} ({acc.get('account_type')}) -> {ok}")
    except Exception as exc:  # noqa: BLE001
        print(f"Instagram: falhou — {exc}")
    gh = "ok" if os.getenv("DB_ARCHIVE_GITHUB_TOKEN") else "FALTANDO"
    print(f"GitHub (hospedagem temporaria p/ Instagram): {gh}")


def _gh() -> tuple[dict, str]:
    tok = (os.getenv("DB_ARCHIVE_GITHUB_TOKEN") or "").strip()
    if not tok:
        raise RuntimeError("DB_ARCHIVE_GITHUB_TOKEN ausente (hospedagem temporaria para o Instagram)")
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    user = requests.get("https://api.github.com/user", headers=h, timeout=30).json().get("login")
    repo = f"{user}/{MEDIA_REPO}"
    if requests.get(f"https://api.github.com/repos/{repo}", headers=h, timeout=30).status_code == 404:
        requests.post("https://api.github.com/user/repos", headers=h, timeout=30, json={
            "name": MEDIA_REPO, "private": False, "auto_init": True,
            "description": "Staging temporario de midia (apagado apos publicar)"})
        time.sleep(2)
    return h, repo


def _stage(repo: str, files: dict[str, Path | str]) -> None:
    tok = (os.getenv("DB_ARCHIVE_GITHUB_TOKEN") or "").strip()
    tmp = Path(tempfile.mkdtemp(prefix="igstage_"))
    try:
        for name, src in files.items():
            if isinstance(src, Path):
                shutil.copyfile(src, tmp / name)
            else:
                (tmp / name).write_text(src, encoding="utf-8")
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        for args in (["init", "-b", "main"], ["config", "user.email", "bot@local"],
                     ["config", "user.name", "bot"], ["add", "-A"], ["commit", "-m", "stage"],
                     ["push", "--force", f"https://x-access-token:{tok}@github.com/{repo}.git", "main:main"]):
            r = subprocess.run(["git", *args], cwd=tmp, capture_output=True, text=True, env=env, timeout=600)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _unstage(repo: str) -> None:
    _stage(repo, {"README.md": "# staging\n"})


def _wait(container: str, tok: str, api: str = IG_API) -> str:
    for _ in range(90):
        r = requests.get(f"{api}/{container}", params={"fields": "status_code", "access_token": tok}, timeout=30)
        code = (r.json() or {}).get("status_code") if r.ok else None
        if code in ("FINISHED", "ERROR", "EXPIRED"):
            return code
        time.sleep(5)
    return "TIMEOUT"


GH_MAX = 90 * 1024 * 1024  # GitHub recusa arquivo > 100 MB


def _ig_video(video: Path) -> Path:
    """Copia leve p/ o Instagram (o staging no GitHub aceita ate 100 MB; o IG recomprime de todo jeito)."""
    if video.stat().st_size <= GH_MAX:
        return video
    from . import ffmpeg
    out = video.parent / "_work" / f"{video.stem}_ig.mp4"
    if out.exists() and out.stat().st_mtime >= video.stat().st_mtime and out.stat().st_size <= GH_MAX:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = ffmpeg.probe_duration(video)
    kbps = int(GH_MAX * 8 / 1024 / dur * 0.85) - 192   # margem; audio 192k
    kbps = min(kbps, 8000)
    print(f"  [instagram] gerando copia leve ({kbps} kbps) para o envio")
    ffmpeg.run(["-i", str(video), "-c:v", "libx264", "-preset", "medium", "-b:v", f"{kbps}k",
                "-maxrate", f"{int(kbps * 1.3)}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                "-movflags", "+faststart", str(out)])
    return out


def instagram_reel(video: Path, caption: str) -> str:
    video = _ig_video(video)
    api, me, tok = _ig()
    _h, repo = _gh()
    name = f"{int(time.time())}_{video.name}"
    _stage(repo, {name: video, "README.md": "# staging\n"})
    try:
        url = f"https://raw.githubusercontent.com/{repo}/main/{name}"
        r = requests.post(f"{api}/{me}/media", timeout=120, data={
            "media_type": "REELS", "video_url": url, "caption": caption[:2200], "access_token": tok})
        r.raise_for_status()
        cid = r.json()["id"]
        if _wait(cid, tok, api) != "FINISHED":
            raise RuntimeError("Instagram nao terminou de processar o Reel")
        r = requests.post(f"{api}/{me}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
        r.raise_for_status()
        print(f"  [instagram] Reel publicado: {r.json().get('id')}")
        return r.json().get("id")
    finally:
        _unstage(repo)


def instagram_carousel(images: list[Path], caption: str) -> str:
    api, me, tok = _ig()
    _h, repo = _gh()
    images = images[:20]  # limite do Instagram
    stamp = int(time.time())
    files = {f"{stamp}_{p.name}": p for p in images}
    files["README.md"] = "# staging\n"
    _stage(repo, files)
    try:
        children = []
        for name in [n for n in files if n != "README.md"]:
            r = requests.post(f"{api}/{me}/media", timeout=60, data={
                "image_url": f"https://raw.githubusercontent.com/{repo}/main/{name}",
                "is_carousel_item": "true", "access_token": tok})
            r.raise_for_status()
            children.append(r.json()["id"])
        r = requests.post(f"{api}/{me}/media", timeout=60, data={
            "media_type": "CAROUSEL", "children": ",".join(children),
            "caption": caption[:2200], "access_token": tok})
        r.raise_for_status()
        cid = r.json()["id"]
        _wait(cid, tok, api)
        r = requests.post(f"{api}/{me}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
        r.raise_for_status()
        print(f"  [instagram] carrossel publicado: {r.json().get('id')}")
        return r.json().get("id")
    finally:
        _unstage(repo)


def _jpg(src: Path) -> Path:
    """A API do Instagram so aceita JPEG em imagem."""
    if src.suffix.lower() in (".jpg", ".jpeg"):
        return src
    from PIL import Image
    out = Path(tempfile.mkdtemp(prefix="igjpg_")) / (src.stem + ".jpg")
    Image.open(src).convert("RGB").save(out, quality=93)
    return out


def _ig_single(image: Path, *, caption: str = "", story: bool = False) -> str:
    """Post de UMA imagem no feed, ou Story (story=True)."""
    image = _jpg(image)
    api, me, tok = _ig()
    _h, repo = _gh()
    name = f"{int(time.time())}_{image.name}"
    _stage(repo, {name: image, "README.md": "# staging\n"})
    try:
        data = {"image_url": f"https://raw.githubusercontent.com/{repo}/main/{name}", "access_token": tok}
        if story:
            data["media_type"] = "STORIES"
        else:
            data["caption"] = caption[:2200]
        r = requests.post(f"{api}/{me}/media", timeout=120, data=data)
        r.raise_for_status()
        cid = r.json()["id"]
        _wait(cid, tok, api)
        r = requests.post(f"{api}/{me}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
        r.raise_for_status()
        print(f"  [instagram] {'Story' if story else 'post'} publicado: {r.json().get('id')}")
        return r.json().get("id")
    finally:
        _unstage(repo)


def instagram_image(image: Path, caption: str) -> str:
    return _ig_single(image, caption=caption)


def instagram_story(image: Path) -> str:
    return _ig_single(image, story=True)


def guard_accounts(cfg: Config, *, youtube: bool, instagram: bool) -> None:
    """Trava de conta: nunca publicar no canal/perfil errado."""
    if youtube:
        want = str(cfg.get("youtube.channel_id", "") or "")
        ch = yt_channel()
        if not want or ch["id"] != want:
            raise SystemExit(f"YouTube logado em '{ch['title']}' ({ch['id']}), esperado '{want}'")
    if instagram:
        want = str(cfg.get("instagram.username", "") or "").lstrip("@").lower()
        got = ig_account().get("username", "").lower()
        if got != want:
            raise SystemExit(f"Instagram logado em @{got}, esperado @{want}")


# --------------------------------------------------------------------------
# orquestracao
# --------------------------------------------------------------------------
def publish(cfg: Config, ep_id: str, *, youtube: bool, instagram: bool, yes: bool) -> None:
    out = ROOT / "output" / ep_id
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    src_yaml = ROOT / "story" / f"{ep_id}.yaml"
    if src_yaml.exists():  # textos sempre do roteiro atual (editar texto nao exige re-render)
        import yaml
        pub = (yaml.safe_load(src_yaml.read_text(encoding="utf-8")) or {}).get("publish")
        if pub:
            meta["publish"] = pub
            if pub.get("instagram_caption") and (out / "carousel").exists():
                (out / "carousel" / "caption.txt").write_text(pub["instagram_caption"], encoding="utf-8")
            if pub.get("tiktok_caption"):  # TikTok e manual: texto pronto para colar
                (out / "tiktok.txt").write_text(pub["tiktok_caption"].strip() + "\n", encoding="utf-8")
                print(f"  [tiktok] legenda pronta em output/{ep_id}/tiktok.txt (envio manual)")
    st = load_status(ep_id)
    video, srt = out / meta["video"], out / meta["srt"]
    slides = sorted((out / "carousel").glob("*.jpg"))
    caption = (out / "carousel" / "caption.txt").read_text(encoding="utf-8") if (out / "carousel" / "caption.txt").exists() else ""

    print(f"Episodio {ep_id}: {video.name} ({meta['duration']}s), {len(slides)} slides")
    print(f"  aprovado: {st.get('approved', False)}")
    blockers = []
    if not st.get("approved"):
        blockers.append(f"episodio nao aprovado (python main.py approve {ep_id})")
    if youtube and not cfg.get("youtube.enabled"):
        blockers.append("youtube.enabled = false no config.yaml")
    if instagram and not cfg.get("instagram.enabled"):
        blockers.append("instagram.enabled = false no config.yaml")
    if blockers or not yes:
        print("\nDRY RUN — nada foi publicado.")
        for b in blockers:
            print(f"  bloqueio: {b}")
        if not yes:
            print("  (falta --yes para publicar de verdade)")
        print(f"\n  titulo YouTube: {meta['publish'].get('title')}")
        return

    # trava de conta: nunca publicar no canal/perfil errado (ex.: o do Bem na Mosca)
    if youtube:
        want = str(cfg.get("youtube.channel_id", "") or "")
        ch = yt_channel()
        if not want or ch["id"] != want:
            raise SystemExit(f"YouTube logado em '{ch['title']}' ({ch['id']}), esperado youtube.channel_id="
                             f"'{want}'. Rode: python main.py check")
    if instagram:
        want = str(cfg.get("instagram.username", "") or "").lstrip("@").lower()
        got = ig_account().get("username", "").lower()
        if got != want:
            raise SystemExit(f"Instagram logado em @{got}, esperado @{want}")

    pubs = st.setdefault("published", {})
    if youtube and "youtube" not in pubs:
        pubs["youtube"] = youtube_upload(cfg, video, meta, srt)
        save_status(ep_id, st)
    if instagram and "instagram_reel" not in pubs:
        pubs["instagram_reel"] = instagram_reel(video, meta["publish"].get("instagram_caption", caption))
        save_status(ep_id, st)
    if instagram and "instagram_carousel" not in pubs and slides:
        pubs["instagram_carousel"] = instagram_carousel(slides, caption)
        save_status(ep_id, st)
    print("publicado:", pubs)
