"""Roteiro para LEITURA/REVISAO do autor: output/epNN/ROTEIRO.md (cena por cena, com a imagem,
quem fala e o texto, sem as marcacoes de atuacao). Abra no VS Code com "Open Preview" (Ctrl+Shift+V).

  python main.py roteiro ep15
"""
from __future__ import annotations

from pathlib import Path

from .config import ROOT, load_config
from .elevenlabs import strip_tags
from .story import episode

NOMES = {"narrador": "Narrador (Davi adulto)", "pensamento": "Pensamento do Davi", "davi": "Davi",
         "mae": "Mãe", "pai": "Pai", "camila": "Camila", "primos": "Primos", "tia": "Tia",
         "gerente": "Gerente (Seu Roberto)", "colega": "Thiago (colega)", "jornaleiro": "Jornaleiro",
         "recrutadora": "Moça do RH (telefone)", "diretor_sonho": "Diretor (sonho)", "menino": "Menino",
         "amigo_escola": "Bruno", "porteiro": "Porteiro", "clara": "Teacher Clara"}
CARD = {"title": "CARTELA DE TÍTULO", "shock": "CHOQUE DE REALIDADE (transição)", "question": "PERGUNTA FINAL"}


def build(ep_id: str) -> Path:
    ep = episode(ep_id)
    out_dir = ROOT / "output" / ep_id
    md = [f"# {ep['title']}", "",
          f"Episódio {ep['number']} · fonte: `{ep.get('source', '')}` · "
          f"imagens: `output/{ep_id}/frames/`", "",
          "> Para comentar: me diga o número da cena (ex.: **s08**) e o que mudar — texto, imagem ou ordem.", ""]
    total = 0
    for sh in ep["shots"]:
        sid = sh["id"]
        if sh.get("card"):
            extra = f" — estilo `{sh['style']}`" if sh.get("style") else ""
            md += [f"## {sid} · {CARD.get(sh['card'], sh['card'])}{extra}", ""]
        else:
            look = {"dream": "✨ sonho", "real": "realidade", "night": "noite"}.get(sh.get("look", ""), sh.get("look", ""))
            md += [f"## {sid} · {sh.get('location', '')} · {look}", ""]
            img = out_dir / "frames" / f"{sid}.png"
            if img.exists():
                md += [f'<img src="frames/{sid}.png" width="260">', ""]
            if sh.get("reuse"):
                md += [f"_(imagem reaproveitada de `{sh['reuse']}`)_", ""]
        for ln in sh.get("lines") or []:
            txt = strip_tags(ln.get("text", "")).strip()
            txt = " ".join(txt.split())
            total += len(txt)
            md += [f"**{NOMES.get(ln['who'], ln['who'])}:** {txt}", ""]
        md += ["---", ""]
    cap = load_config().get("tts.monthly_cap", 0)
    md += [f"_Texto falado: ~{total} caracteres de voz (cota mensal do Dorama: {cap})._", ""]
    pub = ep.get("publish") or {}
    md += ["## Textos de divulgação", "", f"**YouTube — título:** {pub.get('title', '')}", "",
           "**TikTok:**", "", "```", (pub.get("tiktok_caption") or "").strip(), "```", ""]
    out = out_dir / "ROTEIRO.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    return out
