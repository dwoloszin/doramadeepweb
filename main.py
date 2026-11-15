"""Dorama da Deep Web — video-novela em Shorts + carrossel + audiobook.

Fluxo de um episodio (ex.: ep01):
  python main.py refs                 # gera/valida referencias de personagens e lugares (1x)
  python main.py frames ep01          # imagens das cenas (cache: so gera o que mudou)
  python main.py frames ep01 s13 s15 --force   # refaz cenas especificas (lote batch, metade do preco)
  python main.py frames ep01 s13 --force --now # refaz NA HORA (preco cheio)
  python main.py video ep01           # narracao + legendas + video final + audiobook
  python main.py video ep01 --retake s07 s11   # regrava a voz dessas cenas
  python main.py carousel ep01        # carrossel do capitulo (Instagram 4:5)
  python main.py all ep01             # frames + video + carrossel
  python main.py teaser ep01          # "alerta de spoiler" (bloco teaser: do episodio)
  python main.py teaser ep01 t2 --force   # refaz um teaser (imagem nova sai de novo)
  python main.py approve ep01         # voce aprova depois de assistir
  python main.py autopilot --dry      # o que o agendador faria hoje (schedule.yaml), sem publicar
  python main.py media-push ep02 ep03 # sobe video/frames/carrossel/teasers na release do GitHub
  python main.py publish ep01 --youtube --instagram        # dry run
  python main.py publish ep01 --youtube --instagram --yes  # publica (se habilitado)
"""
from __future__ import annotations

import argparse
import sys

from src.config import load_config


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["voices", "check", "refs", "frames", "video", "carousel", "teaser", "all", "autopilot", "tiktok", "roteiro", "media-push", "media-pull", "approve", "unapprove", "publish", "status"])
    ap.add_argument("ep", nargs="?")
    ap.add_argument("ids", nargs="*", help="cenas (frames) ou personagem/lugar (refs)")
    ap.add_argument("--force", action="store_true", help="refaz mesmo com cache/trava")
    ap.add_argument("--youtube", action="store_true")
    ap.add_argument("--instagram", action="store_true")
    ap.add_argument("--yes", action="store_true", help="confirma a publicacao")
    ap.add_argument("--now", action="store_true",
                    help="frames: gera na hora (preco cheio) em vez do lote batch (metade do preco)")
    ap.add_argument("--dry", action="store_true", help="autopilot: so mostra o que faria")
    ap.add_argument("--no-render", action="store_true", help="autopilot: nao renderiza episodios novos")
    ap.add_argument("--light", action="store_true", help="media-push: so imagens (sem o video)")
    ap.add_argument("--render-only", action="store_true", help="autopilot: so renderiza (nao publica)")
    ap.add_argument("--retake", nargs="+", default=[], metavar="CENA",
                    help="video: regrava a voz dessas cenas (nova 'tomada' do ElevenLabs)")
    a = ap.parse_args()

    if a.cmd == "voices":
        from src import elevenlabs
        print("ElevenLabs:")
        print(elevenlabs.status())
        return
    if a.cmd == "check":
        from src import publish
        publish.check(load_config())
        return
    if a.cmd == "refs":
        from src import story
        only = a.ep  # aqui o 1o argumento e o id do personagem/lugar
        story.build_refs(story.bible(), only=only, force=a.force)
        return
    if a.cmd == "autopilot":
        from src import autopilot
        autopilot.run(dry=a.dry, render=not a.no_render, publish_today=not a.render_only)
        return
    if a.cmd == "status":  # painel de andamento: output/STATUS.md
        from src import painel
        print("  ->", painel.build())
        return
    if a.cmd == "roteiro":  # versao de leitura p/ o autor revisar (output/epNN/ROTEIRO.md)
        from src import roteiro
        for ep in [x for x in [a.ep, *a.ids] if x]:
            print("  ->", roteiro.build(ep))
        return
    if a.cmd == "tiktok":  # datas nos textos do TikTok + calendario completo
        import yaml as _y
        from src import calendario, carousel, teaser
        eps = [a.ep, *a.ids] if a.ep else list(_y.safe_load(open("schedule.yaml", encoding="utf-8")).get("episodes") or {})
        for ep in eps:
            carousel.build(ep)
            teaser.build(ep)
        print("  ->", calendario.calendario())
        return
    if a.cmd in ("media-push", "media-pull"):
        from src import media
        for ep in [x for x in [a.ep, *a.ids] if x]:
            media.push(ep, light=a.light) if a.cmd == "media-push" else media.pull(ep)
        return
    if not a.ep:
        sys.exit("informe o episodio, ex.: ep01")
    if a.cmd in ("frames", "all"):
        from src import story
        cfg = load_config()
        ready = story.build_shot_images(a.ep, only=a.ids or None, force=a.force,
                                        batch=bool(cfg.get("images.batch", True)) and not a.now,
                                        wait=float(cfg.get("images.batch_wait_minutes", 30)) * 60)
        if not ready:
            sys.exit("imagens ainda no lote do Gemini — rode o mesmo comando mais tarde para continuar")
    if a.cmd in ("video", "all"):
        from src import render
        render.build(a.ep, retake=set(a.retake))
    if a.cmd in ("carousel", "all"):
        from src import carousel
        carousel.build(a.ep)
    if a.cmd == "teaser":
        from src import teaser
        teaser.build(a.ep, only=a.ids or None, force=a.force)
    if a.cmd in ("approve", "unapprove"):
        from src import publish
        publish.approve(a.ep, a.cmd == "approve")
    if a.cmd == "publish":
        from src import publish
        publish.publish(load_config(), a.ep, youtube=a.youtube, instagram=a.instagram, yes=a.yes)


if __name__ == "__main__":
    main()
