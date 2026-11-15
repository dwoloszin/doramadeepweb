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
         "amigo_escola": "Bruno", "porteiro": "Porteiro", "clara": "Teacher Clara", "eva": "Eva", "menino": "Menino"}
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
    _html(ep, ep_id, out_dir, total, cap)
    return out


def _html(ep: dict, ep_id: str, out_dir: Path, total: int, cap) -> Path:
    """ROTEIRO.html: mesma leitura, com a imagem grande ao lado do texto (abrir no navegador)."""
    import html as H
    cores = {"narrador": "#c9a227", "pensamento": "#8e7cc3", "davi": "#4a90d9"}
    cenas = []
    for sh in ep["shots"]:
        sid = sh["id"]
        if sh.get("card"):
            extra = f" · estilo {sh['style']}" if sh.get("style") else ""
            head, img = f"{CARD.get(sh['card'], sh['card'])}{extra}", '<div class="card">🎬</div>'
        else:
            look = {"dream": "✨ sonho", "real": "realidade", "night": "noite"}.get(sh.get("look", ""), sh.get("look", ""))
            head = f"{sh.get('location', '')} · {look}"
            f = out_dir / "frames" / f"{sid}.png"
            img = (f'<a href="frames/{sid}.png" target="_blank"><img src="frames/{sid}.png" loading="lazy"></a>'
                   if f.exists() else '<div class="card">sem imagem</div>')
            if sh.get("reuse"):
                head += f" · reaproveitada de {sh['reuse']}"
        falas = "".join(
            f'<p><b style="color:{cores.get(ln["who"], "#e06c75")}">{H.escape(NOMES.get(ln["who"], ln["who"]))}:</b> '
            f'{H.escape(" ".join(strip_tags(ln.get("text", "")).split()))}</p>'
            for ln in sh.get("lines") or []) or '<p class="mudo">(sem fala)</p>'
        cenas.append(f'<section><div class="img">{img}</div><div class="txt"><h2><span>{sid}</span> {H.escape(head)}</h2>'
                     f'{falas}</div></section>')
    pub = ep.get("publish") or {}
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{H.escape(ep_id)} roteiro</title>
<style>
body{{margin:0;background:#14121a;color:#eee;font:17px/1.55 system-ui,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:24px 16px}}
h1{{color:#c9a227;margin:0 0 4px}} .sub{{color:#999;margin-bottom:24px}}
section{{display:flex;gap:20px;background:#1e1b26;border-radius:12px;padding:16px;margin:14px 0}}
.img{{flex:0 0 260px}} .img img{{width:260px;border-radius:8px;display:block}}
.card{{width:260px;height:120px;border-radius:8px;background:#2a2633;display:flex;align-items:center;justify-content:center;color:#888;font-size:28px}}
h2{{font-size:15px;color:#aaa;margin:0 0 10px;font-weight:500}} h2 span{{background:#c9a227;color:#14121a;border-radius:6px;padding:2px 8px;font-weight:700;margin-right:6px}}
p{{margin:0 0 10px}} .mudo{{color:#777;font-style:italic}}
pre{{white-space:pre-wrap;background:#1e1b26;padding:14px;border-radius:10px}}
@media(max-width:640px){{section{{flex-direction:column}} .img,.img img,.card{{width:100%;flex:none}}}}
</style></head><body><main>
<h1>{H.escape(ep['title'])}</h1>
<div class="sub">Episódio {ep['number']} · ~{total} caracteres de voz (cota mensal: {cap}) · clique na imagem para ampliar ·
para comentar, diga o número da cena (ex.: s08)</div>
{''.join(cenas)}
<h2 style="margin-top:30px">Textos de divulgação</h2>
<p><b>YouTube — título:</b> {H.escape(pub.get('title', ''))}</p>
<pre>{H.escape((pub.get('tiktok_caption') or '').strip())}</pre>
</main></body></html>"""
    p = out_dir / "ROTEIRO.html"
    p.write_text(doc, encoding="utf-8")
    return p
