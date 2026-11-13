"""Biblia + episodio -> referencias de personagem/lugar e prompts de cena."""
from __future__ import annotations

from pathlib import Path

from . import gemini_image
from .config import ROOT, load_yaml

CHAR_DIR = ROOT / "assets" / "characters"
LOC_DIR = ROOT / "assets" / "locations"
PROP_DIR = ROOT / "assets" / "props"


def bible() -> dict:
    return load_yaml(ROOT / "story" / "bible.yaml")


def episode(ep: str) -> dict:
    return load_yaml(ROOT / "story" / f"{ep}.yaml")


# --------------------------------------------------------------------------
# referencias
# --------------------------------------------------------------------------
def face_ref(cid: str) -> Path:
    return CHAR_DIR / cid / "_face.png"


IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def model_refs(cid: str) -> list[Path]:
    """Fotos-modelo que VOCE coloca em assets/characters/<id>/modelo/ (1 a 3).

    Se existirem, o retrato-base do personagem nasce delas (mesmo rosto)."""
    d = CHAR_DIR / cid / "modelo"
    return sorted(p for p in d.glob("*") if p.suffix.lower() in IMG_EXT)[:3] if d.exists() else []


def outfit_ref(cid: str, outfit: str) -> Path:
    return CHAR_DIR / cid / f"{outfit}.png"


def loc_ref(lid: str) -> Path:
    return LOC_DIR / f"{lid}.png"


def prop_ref(pid: str) -> Path:
    return PROP_DIR / f"{pid}.png"


def _from_frames(item: dict) -> list[Path]:
    """Imagens de cenas ja aprovadas que DEFINEM o visual (continuidade com o que o publico viu)."""
    return [ROOT / f for f in (item.get("from_frames") or []) if (ROOT / f).exists()][:3]


def build_refs(b: dict, *, only: str | None = None, force: bool = False) -> list[Path]:
    """Gera (uma vez) rosto-base, folhas de roupa e fotos dos lugares."""
    style = b["style"]["global"]
    made: list[Path] = []
    for cid, c in b["characters"].items():
        if only and only != cid:
            continue
        face = face_ref(cid)
        # foto-modelo do usuario (se houver) define o rosto; davi_sonho nasce do Davi
        # real -> mesma pessoa, versao idealizada
        models = model_refs(cid)
        base_refs = list(models)
        if cid == "davi_sonho" and face_ref("davi").exists():
            base_refs = [face_ref("davi")] + model_refs("davi")[:1]
        print(f"  [refs] {cid}: retrato-base" + (f" (a partir de {len(models)} foto(s)-modelo)" if models else ""))
        if models:
            lead = ("The reference photo(s) show the MODEL for this character: keep exactly the same "
                    "person — same face shape, eyes, nose, mouth, skin tone, hair. ")
        elif base_refs:
            lead = ("Use the reference image as the SAME person (same face, eyes, skin tone, "
                    "freckles, hair), but follow the description below for build and style. ")
        else:
            lead = ""
        gemini_image.generate(
            lead +
            f"Studio portrait photo, head and shoulders, facing the camera, neutral soft "
            f"grey background, soft even light, calm expression. {c['identity']} "
            f"Wearing a plain neutral grey t-shirt. Photorealistic, 85mm lens, natural skin "
            f"texture. No text, no watermark.",
            face, refs=base_refs, aspect="3:4", force=force, lock=True)
        made.append(face)
        for oid, odesc in (c.get("wardrobe") or {}).items():
            out = outfit_ref(cid, oid)
            print(f"  [refs] {cid}: roupa '{oid}'")
            gemini_image.generate(
                "CHARACTER REFERENCE SHEET. Reference image(s) = the exact same person: copy the "
                "face, eyes, skin tone, hair and BODY TYPE (weight, belly, build) exactly. "
                "Ignore the clothes in the reference photos. "
                f"Character: {c['identity']} "
                f"Outfit (must be shown clearly, every detail): {odesc} "
                "Layout on a plain light-grey studio background, three views side by side: "
                "full body front view, full body three-quarter view, and a close-up of the face. "
                "Same person and same clothes in all three views. Photorealistic, even soft studio "
                "light. No text, no letters on patches or crests, no labels, no watermark.",
                out, refs=[face] + model_refs(cid)[:1], aspect="16:9", force=force, lock=True)
            made.append(out)
    for lid, loc in b["locations"].items():
        if only and only != lid:
            continue
        out = loc_ref(lid)
        print(f"  [refs] lugar '{lid}'")
        src = _from_frames(loc)
        lead = ("The reference image(s) are scenes already shown to the audience: recreate EXACTLY the "
                "same place (same architecture, materials, colors, objects, wear), now empty. ") if src else ""
        gemini_image.generate(
            lead + f"Establishing shot of an empty location, no people. {loc['description']} "
            f"{b['style']['looks'][loc['look']]} {style}",
            out, refs=src, aspect="9:16", force=force, lock=True)
        made.append(out)
    # objetos recorrentes (bicicleta, Kombi, mochila...): folha de referencia
    for pid, pr in (b.get("props") or {}).items():
        if only and only != pid:
            continue
        out = prop_ref(pid)
        print(f"  [refs] objeto '{pid}'")
        src = _from_frames(pr)
        lead = ("The reference image(s) are scenes already shown to the audience: copy EXACTLY this "
                "object from them (same model, shape, colors, wear, dents, details). ") if src else ""
        gemini_image.generate(
            lead + "OBJECT REFERENCE SHEET on a plain light-grey studio background: the same single object "
            "shown in three views side by side (front, side, three-quarter), no people. "
            f"Object: {pr['description']} Photorealistic, even soft studio light. "
            "No text, no letters, no logos, no watermark.",
            out, refs=src, aspect="16:9", force=force, lock=True)
        made.append(out)
    return made


# --------------------------------------------------------------------------
# cenas
# --------------------------------------------------------------------------
def shot_prompt(b: dict, ep: dict, shot: dict) -> tuple[str, list[Path]]:
    """Prompt + referencias de UMA cena, ja com a roupa do dia de cada personagem."""
    day = ep["days"][shot["day"]]
    refs: list[Path] = []
    lines: list[str] = []
    for cid in shot.get("cast", []):
        c = b["characters"][cid]
        outfit = day["wardrobe"][cid]
        ref = outfit_ref(cid, outfit)
        if not ref.exists():
            raise FileNotFoundError(f"referencia ausente: {ref} (rode `python main.py refs`)")
        refs.append(ref)
        n = len(refs)
        lines.append(
            f"{c['name'].upper()} = the person in reference image {n}. Keep EXACTLY the same face, "
            f"hair, skin tone, body type{', glasses' if 'glasses' in c['identity'] and 'No glasses' not in c['identity'] else ''} "
            f"and EXACTLY the same clothes as in reference image {n}: {b['characters'][cid]['wardrobe'][outfit]}")
    # FIGURANTES: o rosto das referencias e SO dos personagens do elenco.
    if shot.get("cast"):
        names = ", ".join(b["characters"][c]["name"] for c in shot["cast"])
        lines.append(
            f"OTHER PEOPLE: only {names} use the faces from the reference images, and each appears only "
            f"once. ANY other person in the frame (extras, passersby, guards, workers, clerks, background "
            f"people) must be a clearly DIFFERENT individual: different face, age, hairstyle, skin tone and "
            f"body type from {names} and from each other. Never copy the reference faces onto anyone else.")
    for pid in shot.get("props", []) or []:
        pr = b["props"][pid]
        ref = prop_ref(pid)
        if not ref.exists():
            raise FileNotFoundError(f"referencia ausente: {ref} (rode `python main.py refs {pid}`)")
        refs.append(ref)
        lines.append(f"{pr.get('name', pid).upper()} = the object in reference image {len(refs)}. Keep EXACTLY "
                     f"the same object (model, colors, wear, details): {pr['description']}")
    loc = b["locations"][shot["location"]]
    lref = loc_ref(shot["location"])
    if lref.exists():
        refs.append(lref)
        lines.append(f"LOCATION = the same place as reference image {len(refs)} "
                     f"(same architecture, colors and objects): {loc['description']}")
    else:
        lines.append(f"LOCATION: {loc['description']}")
    look = b["style"]["looks"][shot.get("look") or loc["look"]]
    time_of_day = shot.get("time") or day.get("time", "")
    prompt = (
        "Create ONE single cinematic film still (one frame, not a collage, not a reference sheet).\n"
        f"SCENE: {shot['visual']}\n"
        + ("\n".join(lines) + "\n")
        + (f"TIME: {time_of_day}\n" if time_of_day else "")
        + f"LOOK: {look}\n{b['style']['global']}"
    )
    return prompt, refs


VOICE_ONLY = {"narrador", "pensamento"}


def validate(ep_id: str) -> list[str]:
    """Regras de continuidade de ELENCO. Erros param a geracao; avisos so informam.

    * personagem recorrente citado no `visual` (pelos `aliases` da biblia) TEM que estar no
      `cast` -> senao o Gemini inventa outra pessoa (outro porteiro, outro pai...).
    * quem fala (`who`) deve estar no `cast` da cena, ou em `offscreen: [id]` (voz fora do quadro).
    """
    import re
    b, ep = bible(), episode(ep_id)
    errors, warns = [], []
    for sh in ep["shots"]:
        if not sh.get("visual"):
            continue
        cast = set(sh.get("cast") or [])
        vis = sh["visual"].lower()
        for cid, c in b["characters"].items():
            for al in c.get("aliases") or []:
                if cid not in cast and re.search(rf"\b{re.escape(al.lower())}\b", vis):
                    errors.append(f"{sh['id']}: o visual cita '{al}' ({cid}) mas '{cid}' nao esta no cast "
                                  f"-> adicione ao cast (mesma pessoa sempre) ou troque a palavra")
        for ln in sh.get("lines") or []:
            who = ln.get("who")
            if who in b["characters"] and who not in cast and who not in (sh.get("offscreen") or []):
                warns.append(f"{sh['id']}: '{who}' fala mas nao esta no cast (use offscreen: [{who}] se for de proposito)")
    for w in warns:
        print(f"  aviso: {w}")
    if errors:
        raise SystemExit("ELENCO inconsistente:\n  " + "\n  ".join(errors))
    return warns


def build_shot_images(ep_id: str, *, only: list[str] | None = None, force: bool = False,
                      image_size: str | None = "2K", batch: bool = True,
                      wait: float = 1800) -> bool:
    """Imagens das cenas. batch=True: um lote (metade do preco), retomavel.
    Devolve True quando TODAS as cenas tem imagem (pode montar o video)."""
    validate(ep_id)
    b, ep = bible(), episode(ep_id)
    out_dir = ROOT / "output" / ep_id / "frames"
    state = ROOT / "output" / ep_id / "_work" / "batch.json"
    just_polled: set[str] = set()
    if state.exists():
        import json as _json
        just_polled = {j["key"] for j in _json.loads(state.read_text(encoding="utf-8"))["jobs"]}
        if not gemini_image.batch_poll(state, wait=wait):
            return False
        force = False  # o que o lote entregou ja e a versao nova
    jobs = []
    for shot in ep["shots"]:
        if not shot.get("visual"):
            continue
        if only and shot["id"] not in only:
            continue
        out = out_dir / f"{shot['id']}.png"
        prompt, refs = shot_prompt(b, ep, shot)
        fp = gemini_image.needs(prompt, out, refs, "9:16", image_size, force)
        if fp:
            jobs.append({"key": shot["id"], "prompt": prompt, "out": out, "refs": refs,
                         "aspect": "9:16", "image_size": image_size, "fp": fp})
    if not jobs:
        return True
    # o que falhou no lote anterior (ou modo --now) sai na hora, preco normal
    sync = jobs if not batch else [j for j in jobs if j["key"] in just_polled]
    for j in sync:
        print(f"  [cena] {j['key']} (na hora)")
        gemini_image.generate(j["prompt"], j["out"], refs=j["refs"], aspect="9:16",
                              force=True, image_size=image_size)
    rest = [j for j in jobs if j not in sync]
    if not rest:
        return True
    print(f"  [cena] {', '.join(j['key'] for j in rest)} -> lote")
    gemini_image.batch_submit(rest, state, label=f"doramadeepweb-{ep_id}")
    return gemini_image.batch_poll(state, wait=wait)
