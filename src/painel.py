"""Painel de andamento: output/STATUS.md (atualizado a cada execucao do autopilot e por
`python main.py status`). Mostra, por episodio: roteiro, imagens, voz+video, aprovacao,
data e o que ja saiu — e quanto credito de voz falta para os que estao esperando.
"""
from __future__ import annotations

import datetime as dt
import json

from .config import ROOT

OUT = ROOT / "output" / "STATUS.md"


def _num(ep: str) -> int:
    return int(ep[2:])


def _assets(ep: str) -> list[str]:
    from . import media
    r = media._gh("release", "view", media.tag(ep), "--json", "assets", "-q", ".assets[].name", check=False)
    return r.stdout.split() if r.returncode == 0 else []


def build(check_credits: bool = True) -> str:
    import yaml

    from . import elevenlabs, publish, story
    sched = yaml.safe_load((ROOT / "schedule.yaml").read_text(encoding="utf-8")) or {}
    dates = {k: str(v) for k, v in (sched.get("episodes") or {}).items()}
    have = None
    if check_credits:
        try:
            have, _ = elevenlabs.pool_credits()
        except Exception:  # noqa: BLE001
            have = None
    left = elevenlabs.allowance()
    rows, waiting = [], []
    for y in sorted((ROOT / "story").glob("ep[0-9]*.yaml"), key=lambda p: _num(p.stem)):
        ep = y.stem
        epd = story.episode(ep)
        out = ROOT / "output" / ep
        assets = _assets(ep)
        n_shots = sum(1 for sh in epd["shots"] if not sh.get("card"))
        n_local = len(list((out / "frames").glob("s*.png"))) if (out / "frames").exists() else 0
        imgs = "✅" if (n_local >= n_shots or "frames.zip" in assets) else (f"⏳ {n_local}/{n_shots}" if n_local else "—")
        done = (out / "metadata.json").exists() or f"{ep}.mp4" in assets or (out / f"{ep}.mp4").exists()
        need = elevenlabs.estimate(epd)
        if done:
            video = "✅"
        elif epd.get("hold"):
            video = "⏸️ em espera (hold)"
        else:
            video = f"⏳ aguardando crédito de voz (~{need:.0f})"
            waiting.append((ep, need))
        st = publish.load_status(ep)
        pub = st.get("published") or {}
        saiu = [x for x, k in (("YouTube", "youtube"), ("Instagram", "instagram_reel")) if pub.get(k)]
        rows.append(f"| {ep} | {epd.get('title', '')} | ✅ | {imgs} | {video} | "
                    f"{'✅' if st.get('approved') else '—'} | {dates.get(ep, '—')} | {', '.join(saiu) or '—'} |")
    now = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    md = [f"# Andamento do Dorama — {now}", "",
          "| Ep | Título | Roteiro | Imagens | Voz + vídeo | Aprovado | Data | Já saiu |",
          "|---|---|---|---|---|---|---|---|", *rows, "",
          "## Voz (ElevenLabs)", "",
          f"- Limite mensal do Dorama: {elevenlabs.used():.0f} de {elevenlabs.monthly_cap():.0f} usados em "
          f"{dt.date.today():%m/%Y} → {'sem limite' if left == float('inf') else f'{left:.0f} livres'}",
          f"- Créditos aproveitáveis nas chaves (acima da folga de {elevenlabs.key_min():.0f} por chave; "
          f"chaves reservadas a outro projeto não contam): {'?' if have is None else f'{have:.0f}'}"]
    for ep, need in waiting:
        ok = have is not None and min(have, left) >= need * 1.3
        md.append(f"- {ep}: precisa ~{need * 1.3:.0f} (com folga de 30%) → "
                  f"{'pode renderizar na próxima execução' if ok else 'esperando crédito'}")
    md += ["", "_Quando houver crédito, o GitHub Actions renderiza sozinho e abre uma issue "
           "“pronto para revisão”._", ""]
    OUT.write_text("\n".join(md), encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    print(build())
