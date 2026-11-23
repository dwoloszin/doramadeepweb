"""Piloto automatico: roda todo dia (GitHub Actions, ~12h de Brasilia) e segue o schedule.yaml.

Cada execucao:
  1. RENDER  — episodio com story/epNN.yaml e sem video (nem local, nem na release):
               refs -> frames (lote batch; retoma no dia seguinte) -> video -> carrossel -> teasers
               -> sobe a midia na release media-epNN. NAO publica: espera a sua aprovacao.
  2. AGENDA  — episodio aprovado sem data ganha o proximo domingo livre.
  3. YOUTUBE — episodio aprovado e agendado ainda nao enviado: sobe ja com publishAt no domingo 12h.
  4. INSTAGRAM (no dia): domingo -> Reel + carrossel; terca/quinta/sabado -> teaser (feed + Story).
Tudo o que sai fica registrado em output/epNN/status.json -> published (nunca publica 2x).
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import media, publish
from .config import ROOT, load_config

SCHED = ROOT / "schedule.yaml"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _num(ep_id: str) -> int:
    return int(ep_id[2:])


def load() -> dict:
    return yaml.safe_load(SCHED.read_text(encoding="utf-8")) or {}


def _save_dates(episodes: dict) -> None:
    """Reescreve SO o bloco `episodes:` (mantem os comentarios do arquivo)."""
    text = SCHED.read_text(encoding="utf-8")
    head = text.split("\nepisodes:")[0]
    body = "".join(f"  {ep}: {d}\n" for ep, d in sorted(episodes.items(), key=lambda kv: _num(kv[0])))
    SCHED.write_text(head + "\nepisodes:\n" + body, encoding="utf-8")


def _dates(sched: dict) -> dict[str, dt.date]:
    out = {}
    for ep, d in (sched.get("episodes") or {}).items():
        out[ep] = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
    return out


def plan(sched: dict) -> dict[str, dt.date]:
    """Da data (proximo domingo livre) a todo episodio aprovado que ainda nao tem."""
    dates = _dates(sched)
    first = min((_num(e) for e in dates), default=2)
    wd = WEEKDAYS.index(sched.get("episode_weekday", "sunday"))
    added = []
    for y in sorted((ROOT / "story").glob("ep[0-9]*.yaml"), key=lambda p: _num(p.stem)):
        ep = y.stem
        if ep in dates or _num(ep) < first or not publish.load_status(ep).get("approved"):
            continue
        last = max(dates.values()) if dates else dt.date.today()
        d = last + dt.timedelta(days=1)
        while d.weekday() != wd:
            d += dt.timedelta(days=1)
        dates[ep] = d
        added.append(f"{ep} -> {d}")
    if added:
        _save_dates({k: v.isoformat() for k, v in dates.items()})
        print("  [agenda] " + ", ".join(added))
    return dates


def _slot(sched: dict, day: dt.date, tz: ZoneInfo) -> dt.datetime:
    h, m = map(int, str(sched.get("time", "12:00")).split(":"))
    return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=tz)


def render_missing(dry: bool) -> None:
    """Gera os episodios novos (roteiro pronto, video ainda nao) — nao publica nada."""
    from . import carousel, render, story, teaser
    cfg = load_config()
    for y in sorted((ROOT / "story").glob("ep[0-9]*.yaml"), key=lambda p: _num(p.stem)):
        ep = y.stem
        if media.rendered(ep):
            continue
        epd = story.episode(ep)
        if epd.get("hold"):
            print(f"== {ep}: em espera (hold: true no roteiro) — nao renderiza")
            continue
        # so gasta imagem se HOUVER voz para o episodio inteiro (14/11: sem credito o Actions
        # gerou as imagens do ep15 e travou na voz — desperdicio)
        from . import elevenlabs
        ok, msg = elevenlabs.preflight(elevenlabs.estimate(epd), ep)   # consulta ANTES de qualquer chamada
        if not ok:
            print(f"== {ep}: sem credito de voz suficiente — espera, sem gastar ({msg})")
            continue
        print(f"== render {ep} (novo roteiro, ainda sem video)")
        if dry:
            continue
        media.pull(ep, ("frames",))      # imagens ja geradas localmente: reaproveita (custo zero)
        story.build_refs(story.bible())
        ok = story.build_shot_images(ep, batch=bool(cfg.get("images.batch", True)),
                                     wait=float(cfg.get("images.batch_wait_minutes", 30)) * 60)
        if not ok:
            print(f"  {ep}: imagens ainda no lote do Gemini — continua na proxima execucao")
            continue
        render.build(ep)
        carousel.build(ep)
        if (story.episode(ep).get("teaser")):
            teaser.build(ep)
        media.push(ep)
        _avisar_pronto(ep)
        print(f"  {ep}: PRONTO para revisao (baixe da release {media.tag(ep)}); "
              f"publica so depois de: python main.py approve {ep}")


def _avisar_pronto(ep: str) -> None:
    """Abre uma issue no repositorio -> o GitHub manda e-mail ao autor: episodio pronto p/ revisar."""
    import subprocess
    body = "\n".join([
        f"O **{ep}** foi renderizado pelo GitHub Actions e esta pronto para a sua revisao.",
        "",
        f"- Midia (video, carrossel, teasers): release `{media.tag(ep)}` em Releases",
        f"- Para aprovar: Actions > autopilot > Run workflow > approve: `{ep}` "
        f"(ou `python main.py approve {ep}` local + push)",
        "",
        "Depois de aprovado ele entra no proximo domingo livre do calendario."])
    try:
        subprocess.run(["gh", "issue", "create", "--title", f"🎬 {ep} pronto para revisão", "--body", body],
                       cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
        print(f"  {ep}: aviso enviado (issue no GitHub)")
    except Exception as exc:  # noqa: BLE001
        print(f"  {ep}: nao consegui abrir a issue de aviso: {exc}")


def _teaser_item(ep: str, tid: str) -> dict | None:
    from .story import episode
    for t in episode(ep).get("teaser") or []:
        if t["id"] == tid:
            return t
    return None


def run(*, dry: bool = False, now: dt.datetime | None = None, render: bool = True,
        publish_today: bool = True) -> None:
    """publish_today=False: so renderiza (ex.: push de um roteiro novo)."""
    if publish_today:
        _publish(dry=dry, now=now)
    if render:  # depois de publicar: render demora e nao pode atrasar o horario
        render_missing(dry)
    try:  # painel de andamento (output/STATUS.md)
        from . import painel
        print("  painel:", painel.build())
    except Exception as exc:  # noqa: BLE001
        print(f"  painel falhou: {exc}")


def _publish(*, dry: bool, now: dt.datetime | None) -> None:
    cfg = load_config()
    sched = load()
    tz = ZoneInfo(sched.get("timezone", "America/Sao_Paulo"))
    dates = plan(sched)
    try:  # calendario do TikTok sempre em dia com o schedule
        from .calendario import calendario
        calendario()
    except Exception as exc:  # noqa: BLE001
        print(f"  calendario do TikTok falhou: {exc}")

    now = now or dt.datetime.now(tz)
    today = now.date()
    # o cron do GitHub pode adiantar/atrasar: espera ate o horario (no maximo 45 min)
    slot_today = _slot(sched, today, tz)
    if not dry and dt.timedelta(0) < slot_today - now <= dt.timedelta(minutes=45):
        wait = (slot_today - now).total_seconds()
        print(f"  aguardando o horario ({wait / 60:.0f} min)...")
        time.sleep(wait)
        now = dt.datetime.now(tz)
    after_slot = now >= slot_today
    print(f"autopilot: {now:%a %d/%m/%Y %H:%M} ({tz.key}){' [DRY RUN]' if dry else ''}")

    yt_on, ig_on = bool(cfg.get("youtube.enabled")), bool(cfg.get("instagram.enabled"))
    checked = {"yt": False, "ig": False}
    yt_budget = 3   # cota da API: ~1600 unidades por envio (10 mil/dia) -> no maximo 3 por execucao

    def guard(yt: bool = False, ig: bool = False) -> bool:
        """False = Instagram fora do ar (conta bloqueada/token recusado): pula SO o Instagram,
        o resto (YouTube, render, painel) segue normal e tenta de novo no dia seguinte."""
        if dry:
            return True
        if yt and not checked["yt"]:
            publish.guard_accounts(cfg, youtube=True, instagram=False)
            checked["yt"] = True
        if ig and not checked["ig"]:
            try:
                publish.guard_accounts(cfg, youtube=False, instagram=True)
                checked["ig"] = True
            except Exception as exc:  # noqa: BLE001
                checked["ig"] = "down"
                print(f"  !! Instagram indisponivel — pulando Instagram hoje: {str(exc)[:200]}")
        return not (ig and checked["ig"] == "down")

    # --- YouTube: tudo sobe ANTES, ja agendado (publishAt). Episodios + Shorts de teaser
    #     (ter/qui/sab), em ordem de data, ate `yt_budget` envios por execucao (cota da API).
    jobs = []
    for ep, day in dates.items():
        st = publish.load_status(ep)
        if not st.get("approved"):
            continue
        pubs = st.get("published", {})
        if "youtube" not in pubs and day <= today + dt.timedelta(days=14):
            jobs.append((_slot(sched, day, tz), ep, None))           # atrasado tambem sobe (sai na hora)
        for tid, before in (sched.get("teasers") or {}).items():
            tday = day - dt.timedelta(days=int(before))
            if (f"youtube_{tid}" not in pubs and today <= tday <= today + dt.timedelta(days=14)
                    and _teaser_item(ep, tid)):
                jobs.append((_slot(sched, tday, tz), ep, tid))
    for slot_j, ep, tid in sorted(jobs, key=lambda j: j[0])[:yt_budget if yt_on else 0]:
        when = max(slot_j, now + dt.timedelta(minutes=20))
        print(f"  {ep}: YouTube {'Short teaser ' + tid if tid else 'episodio'} -> agendar para {when:%d/%m %H:%M}")
        if dry:
            continue
        guard(yt=True)
        st = publish.load_status(ep)
        pubs = st.setdefault("published", {})
        out = ROOT / "output" / ep
        if tid:  # Short de teaser: erro aqui NUNCA trava o resto da publicacao do dia
            try:
                from . import teaser_short
                from .story import episode
                media.pull(ep, ("teaser",))
                video = teaser_short.build(ep, tid)
                meta = {"publish": teaser_short.yt_publish(episode(ep), _teaser_item(ep, tid))}
                pubs[f"youtube_{tid}"] = publish.youtube_upload(cfg, video, meta, None, when=when)
                pubs[f"youtube_{tid}_publish_at"] = when.isoformat()
            except Exception as exc:  # noqa: BLE001
                print(f"    Short do teaser {ep} {tid} falhou: {exc}")
                continue
        else:
            media.pull(ep, ("video",))
            meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            pub = (yaml.safe_load((ROOT / "story" / f"{ep}.yaml").read_text(encoding="utf-8")) or {}).get("publish")
            if pub:
                meta["publish"] = pub
            pubs["youtube"] = publish.youtube_upload(cfg, out / meta["video"], meta, out / meta["srt"], when=when)
            pubs["youtube_publish_at"] = when.isoformat()
        publish.save_status(ep, st)
        if not tid:  # episodio novo -> entra na playlist "todos os episodios em ordem"
            try:
                from . import playlist
                playlist.sync(cfg)
            except Exception as exc:  # noqa: BLE001  (nunca trava a publicacao)
                print(f"    playlist falhou: {exc}")

    for ep, day in sorted(dates.items(), key=lambda kv: kv[1]):
        st = publish.load_status(ep)
        pubs = st.setdefault("published", {})
        if not st.get("approved"):
            if day >= today:
                print(f"  {ep} ({day}): NAO aprovado — nada sai (python main.py approve {ep})")
            continue

        # --- Instagram: o episodio no domingo (ou atrasado, se a execucao do dia falhou)
        if ig_on and (today > day or (today == day and after_slot)):
            todo = [k for k in ("instagram_reel", "instagram_carousel") if k not in pubs]
            if todo:
                print(f"  {ep}: Instagram -> {' + '.join(todo)}")
                if not dry and guard(ig=True):
                    media.pull(ep, ("video", "carousel"))
                    out = ROOT / "output" / ep
                    pub = (yaml.safe_load((ROOT / "story" / f"{ep}.yaml").read_text(encoding="utf-8")) or {}).get("publish", {})
                    cap = pub.get("instagram_caption", "")
                    if "instagram_reel" in todo:
                        pubs["instagram_reel"] = publish.instagram_reel(out / f"{ep}.mp4", cap)
                        publish.save_status(ep, st)
                    slides = sorted((out / "carousel").glob("*.jpg"))
                    if "instagram_carousel" in todo and slides:
                        pubs["instagram_carousel"] = publish.instagram_carousel(slides, cap)
                        publish.save_status(ep, st)

        # --- Teasers: so no proprio dia (dia perdido nao acumula)
        for tid, before in (sched.get("teasers") or {}).items():
            tday = day - dt.timedelta(days=int(before))
            key = f"teaser_{tid}"
            if not ig_on or tday != today or not after_slot or key in pubs:
                continue
            item = _teaser_item(ep, tid)
            if not item:
                continue
            print(f"  {ep}: teaser {tid} -> Instagram (feed + Story)")
            if dry:
                continue
            if not guard(ig=True):
                continue
            media.pull(ep, ("teaser",))
            tdir = ROOT / "output" / ep / "teaser"
            feed, story_img = tdir / f"{tid}_feed.png", tdir / f"{tid}_story.png"
            if not feed.exists():
                print(f"    {feed} ausente — pulei")
                continue
            pubs[key] = publish.instagram_image(feed, (item.get("caption") or "").strip())
            publish.save_status(ep, st)
            if story_img.exists():
                try:
                    pubs[f"{key}_story"] = publish.instagram_story(story_img)
                except Exception as exc:  # noqa: BLE001 — Story falhou nao derruba o resto
                    print(f"    Story falhou: {exc}")
                publish.save_status(ep, st)

    # resumo da semana (aparece no log do Actions)
    print("\nproximos 14 dias:")
    for ep, day in sorted(dates.items(), key=lambda kv: kv[1]):
        if today <= day <= today + dt.timedelta(days=14):
            ok = "aprovado" if publish.load_status(ep).get("approved") else "NAO APROVADO"
            print(f"  {day:%a %d/%m} 12h  {ep} ({ok})")
        for tid, before in (sched.get("teasers") or {}).items():
            tday = day - dt.timedelta(days=int(before))
            if today <= tday <= today + dt.timedelta(days=14):
                print(f"  {tday:%a %d/%m} 12h  {ep} teaser {tid}")
