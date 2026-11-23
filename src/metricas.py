"""Metricas do YouTube por video, SEMPRE considerando o tempo no ar (comparacao justa).

  python main.py metricas        # tira a foto de hoje + gera output/METRICAS.md

* Foto diaria (autopilot): views/likes/comentarios de cada video -> output/metricas.json
* "No ar desde" = horario da estreia (publishAt dos agendados), nao o horario do envio.
* Comparacao: views com 1, 3 e 7 dias de ar (foto mais proxima daquela idade) + views/dia.
* `tagset` = conjunto de hashtags usado no video (teste A/B); vem de publish.tagset no epNN.yaml
  ou de teaser_tagset; sem nada = "base".
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .config import ROOT

DB = ROOT / "output" / "metricas.json"
REPORT = ROOT / "output" / "METRICAS.md"
AGES = (1, 3, 7)


def _load() -> dict:
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _videos() -> dict[str, dict]:
    """{video_id: {ep, kind, live_at, tagset}} a partir dos status.json."""
    import yaml
    out = {}
    for st in sorted((ROOT / "output").glob("ep*/status.json")):
        ep = st.parent.name
        pubs = json.loads(st.read_text(encoding="utf-8")).get("published") or {}
        y = ROOT / "story" / f"{ep}.yaml"
        pub = ((yaml.safe_load(y.read_text(encoding="utf-8")) or {}).get("publish") or {}) if y.exists() else {}
        for k, v in pubs.items():
            m = re.fullmatch(r"youtube(?:_(t\d+))?", k)
            if not (m and v):
                continue
            kind = m.group(1) or "episodio"
            tagset = pubs.get(f"{k}_tagset") or "base"
            out[v] = {"ep": ep, "kind": kind, "live_at": pubs.get(f"{k}_publish_at"), "tagset": tagset}
    return out


def snapshot(now: dt.datetime | None = None) -> dict:
    from . import publish
    now = now or dt.datetime.now(dt.timezone.utc)
    db, vids = _load(), _videos()
    svc = publish._yt_service()
    ids = list(vids)
    for i in range(0, len(ids), 50):
        for it in svc.videos().list(part="statistics,status,snippet", id=",".join(ids[i:i + 50])).execute()["items"]:
            v, info = it["id"], vids[it["id"]]
            rec = db.setdefault(v, {})
            rec.update({k: info[k] for k in ("ep", "kind", "tagset")})
            rec["title"] = it["snippet"]["title"]
            rec["tags"] = it["snippet"].get("tags", [])
            rec["hashtags"] = sorted(set(re.findall(r"#\w+", it["snippet"]["title"] + " " +
                                                    it["snippet"].get("description", ""))))
            live = info["live_at"] or it["snippet"]["publishedAt"]
            rec["live_at"] = live
            if it["status"]["privacyStatus"] != "public":
                continue                      # agendado: ainda nao esta no ar
            s = it["statistics"]
            rec.setdefault("snaps", {})[now.strftime("%Y-%m-%dT%H:%M")] = [
                int(s.get("viewCount", 0)), int(s.get("likeCount", 0)), int(s.get("commentCount", 0))]
    try:
        _analytics(db, publish, now)
    except Exception as exc:  # noqa: BLE001  (sem permissao de Analytics: segue so com o basico)
        print(f"  [metricas] Analytics indisponivel: {str(exc)[:150]}")
    DB.parent.mkdir(parents=True, exist_ok=True)
    DB.write_text(json.dumps(db, indent=1, ensure_ascii=False), encoding="utf-8")
    return db


def _analytics(db: dict, publish, now: dt.datetime) -> None:
    """YouTube Analytics (atraso de ~2 dias): retencao, compartilhamentos, inscritos, origem e buscas."""
    from googleapiclient.discovery import build
    svc = publish._yt_service()
    ya = build("youtubeAnalytics", "v2", credentials=svc._http.credentials)
    q = dict(ids="channel==MINE", startDate="2026-11-01", endDate=now.strftime("%Y-%m-%d"))
    r = ya.reports().query(**q, metrics="views,averageViewPercentage,averageViewDuration,shares,subscribersGained",
                           dimensions="video", sort="-views", maxResults=200).execute()
    for vid, views, pct, dur, shares, subs in r.get("rows", []):
        if vid in db:
            db[vid]["analytics"] = {"views": views, "retencao_pct": pct, "dur_media_s": dur,
                                    "compart": shares, "inscritos": subs}
    meta = db.setdefault("_canal", {})
    r = ya.reports().query(**q, metrics="views", dimensions="insightTrafficSourceType", sort="-views").execute()
    meta["origem"] = r.get("rows", [])
    r = ya.reports().query(**q, metrics="views", dimensions="insightTrafficSourceDetail",
                           filters="insightTrafficSourceType==YT_SEARCH", sort="-views", maxResults=25).execute()
    meta["buscas"] = r.get("rows", [])
    meta["atualizado"] = now.strftime("%Y-%m-%d")


def _age_days(live: str, when: str) -> float:
    a = dt.datetime.fromisoformat(live.replace("Z", "+00:00"))
    b = dt.datetime.fromisoformat(when).replace(tzinfo=dt.timezone.utc) if "+" not in when else dt.datetime.fromisoformat(when)
    return (b - a).total_seconds() / 86400


def _at_age(rec: dict, age: float) -> list[int] | None:
    """[views, likes, comentarios] na idade `age` (dias): foto mais proxima entre age e age+1 dia."""
    best = None
    for when, vals in (rec.get("snaps") or {}).items():
        d = _age_days(rec["live_at"], when)
        if age <= d < age + 1 and (best is None or d < best[0]):
            best = (d, vals)
    return best[1] if best else None


def _eng(v: list[int] | None) -> float | None:
    """Engajamento = (likes + comentarios) / views."""
    return None if not v or not v[0] else 100 * (v[1] + v[2]) / v[0]


def report() -> Path:
    db = _load()
    rows = []
    for v, r in db.items():
        if v.startswith("_"):
            continue
        snaps = r.get("snaps") or {}
        if not snaps:
            continue
        last = max(snaps)
        age = max(_age_days(r["live_at"], last), 0.5)
        rows.append((r["ep"], r["kind"], r.get("tagset", "base"), age, snaps[last], [_at_age(r, a) for a in AGES]))
    rows.sort(key=lambda x: (x[0], x[1]))
    f = lambda x: "—" if x is None else str(x)  # noqa: E731
    pc = lambda x: "—" if x is None else f"{x:.1f}%"  # noqa: E731
    md = ["# Desempenho no YouTube (considerando o tempo no ar)", "",
          f"_Atualizado: {dt.datetime.now():%d/%m/%Y %H:%M}. Para comparar vídeos de idades diferentes use as "
          "colunas D1/D3/D7 (números com 1, 3 e 7 dias no ar; — = sem foto naquela idade) ou as taxas por dia. "
          "Engajamento = (likes + comentários) ÷ views._", "",
          "| Ep | Tipo | Hashtags | No ar | Views | Likes | Coment. | Views/dia | Likes/dia | Engaj. "
          "| Views D1/D3/D7 | Likes D1/D3/D7 | Engaj. D3 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for ep, kind, ts, age, (vw, lk, cm), at in rows:
        md.append(f"| {ep} | {kind} | {ts} | {age:.1f} d | {vw} | {lk} | {cm} | {vw / age:.0f} | {lk / age:.1f} | "
                  f"{pc(_eng([vw, lk, cm]))} | {' / '.join(f(a and a[0]) for a in at)} | "
                  f"{' / '.join(f(a and a[1]) for a in at)} | {pc(_eng(at[1]))} |")
    md += ["", "## Média por conjunto de hashtags (mesma idade: 3 dias no ar)", "",
           "| Conjunto | Tipo | Vídeos c/ D3 | Views D3 | Likes D3 | Coment. D3 | Engaj. D3 |",
           "|---|---|---|---|---|---|---|"]
    groups: dict[tuple, list] = {}
    for ep, kind, ts, age, last, at in rows:
        if at[1]:
            groups.setdefault((ts, "episodio" if kind == "episodio" else "teaser"), []).append(at[1])
    for (ts, kind), xs in sorted(groups.items()):
        n = len(xs)
        avg = [sum(x[i] for x in xs) / n for i in range(3)]
        md.append(f"| {ts} | {kind} | {n} | {avg[0]:.0f} | {avg[1]:.1f} | {avg[2]:.1f} | {pc(_eng(avg))} |")
    if not groups:
        md.append("| (ainda sem vídeos com 3 dias de fotos) | | | | | | |")
    md += ["", "## Retenção e crescimento (YouTube Analytics, atraso de ~2 dias)", "",
           "_Retenção = % média do vídeo que a pessoa assiste (no Shorts é o que mais pesa no algoritmo)._", "",
           "| Ep | Tipo | Views | Retenção | Tempo médio | Compart. | Inscritos ganhos |", "|---|---|---|---|---|---|---|"]
    for v, r in sorted(((v, r) for v, r in db.items() if not v.startswith("_") and r.get("analytics")),
                       key=lambda x: (x[1]["ep"], x[1]["kind"])):
        a = r["analytics"]
        md.append(f"| {r['ep']} | {r['kind']} | {a['views']} | {a['retencao_pct']:.0f}% | {a['dur_media_s']}s | "
                  f"{a['compart']} | {a['inscritos']} |")
    canal = db.get("_canal") or {}
    nomes = {"SHORTS": "feed do Shorts", "YT_SEARCH": "busca do YouTube", "YT_CHANNEL": "página do canal",
             "SUBSCRIBER": "inscritos", "NOTIFICATION": "notificações", "PLAYLIST": "playlist",
             "HASHTAGS": "páginas de hashtag", "EXT_URL": "links externos", "RELATED_VIDEO": "vídeos sugeridos"}
    if canal.get("origem"):
        md += ["", "## De onde vêm as views (canal todo)", ""]
        md += [f"- {nomes.get(k, k)}: {n}" for k, n in canal["origem"] if n]
    if canal.get("buscas"):
        md += ["", "## O que as pessoas buscaram para chegar aqui", ""]
        md += [f"- \"{k}\": {n}" for k, n in canal["buscas"]]
    REPORT.write_text(chr(10).join(md) + chr(10), encoding="utf-8")
    return REPORT
