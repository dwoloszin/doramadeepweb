"""Datas de postagem (as MESMAS do schedule.yaml que o GitHub usa p/ YouTube e Instagram).

Usado para escrever a data nos textos do TikTok (envio manual):
  output/epNN/tiktok.txt            -> "POSTAR: domingo 15/11/2026 12h" + legenda do video
  output/epNN/teaser/teaser.txt     -> data em cada bloco t1/t2/t3
  output/CALENDARIO_TIKTOK.txt      -> tudo, dia a dia, com arquivo e texto
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from .config import ROOT

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _sched() -> dict:
    p = ROOT / "schedule.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def datas(ep_id: str) -> dict[str, dt.date]:
    """{'episode': data, 't1': data, ...} — vazio se o episodio ainda nao tem data (nao aprovado)."""
    s = _sched()
    d = (s.get("episodes") or {}).get(ep_id)
    if not d:
        return {}
    d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
    out = {"episode": d}
    for tid, before in (s.get("teasers") or {}).items():
        out[tid] = d - dt.timedelta(days=int(before))
    return out


def quando(ep_id: str, key: str) -> str:
    d = datas(ep_id).get(key)
    hora = str(_sched().get("time", "12:00")).replace(":00", "h")
    if not d:
        return "SEM DATA AINDA (episodio nao aprovado/agendado)"
    return f"{DIAS[d.weekday()]} {d:%d/%m/%Y} {hora}"


def calendario() -> Path:
    from . import hashtags
    """output/CALENDARIO_TIKTOK.txt: cada dia, o que postar, qual arquivo e o texto."""
    s = _sched()
    items = []
    for ep in (s.get("episodes") or {}):
        y = ROOT / "story" / f"{ep}.yaml"
        if not y.exists():
            continue
        data = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
        ds = datas(ep)
        items.append((ds["episode"], 1, ep, "VIDEO", f"output/{ep}/{ep}.mp4",
                      hashtags.add((data.get("publish") or {}).get("tiktok_caption", ""))))
        for t in data.get("teaser") or []:
            if t["id"] in ds:
                kind = "CARTAZ" if t.get("style") == "poster" else "TEASER"
                items.append((ds[t["id"]], 0, ep, f"{kind} {t['id']}",
                              f"output/{ep}/teaser/{t['id']}_short.mp4  (video com voz; ou a foto {t['id']}_story.png)",
                              hashtags.add(t.get("caption", ""))))
    hoje = dt.date.today()
    hora = str(s.get("time", "12:00")).replace(":00", "h")
    lines = ["CALENDARIO DO TIKTOK — mesmas datas do YouTube e do Instagram (schedule.yaml)",
             f"Gerado em {hoje:%d/%m/%Y}. Horario: {hora} (Brasilia). Ja passou = marcado com (passou).", ""]
    for d, _o, ep, kind, arq, txt in sorted(items):
        tag = " (passou)" if d < hoje else ""
        lines += ["=" * 70, f"{DIAS[d.weekday()].upper()} {d:%d/%m/%Y} {hora}{tag} — {ep} — {kind}",
                  f"ARQUIVO: {arq}", "-" * 70, (txt or "").strip(), ""]
    out = ROOT / "output" / "CALENDARIO_TIKTOK.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
