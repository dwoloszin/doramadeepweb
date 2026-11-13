"""Imagens com Gemini — com IMAGENS DE REFERENCIA para manter os personagens.

Como a continuidade e garantida:
  1. Cada personagem ganha um retrato-base (identity) gerado uma unica vez.
  2. Cada roupa da biblia ganha uma folha de referencia (corpo inteiro + rosto)
     gerada A PARTIR do retrato-base -> mesmo rosto em todas as roupas.
  3. Cada lugar ganha uma foto de estabelecimento (sem pessoas).
  4. Toda cena envia junto as folhas dos personagens presentes (com a roupa do
     DIA) + a foto do lugar, e o prompt manda copiar rosto/roupa exatamente.

Tudo e cacheado por hash (prompt + referencias): rodar de novo nao cobra de
novo. Para refazer uma imagem, apague o png (ou use --force).
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path

import requests

_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODELS = ["gemini-3.1-flash-image", "gemini-2.5-flash-image"]


def _key() -> str:
    k = (os.getenv("GEMINI_API_KEY_IMG") or "").strip()
    if not k:
        raise RuntimeError("GEMINI_API_KEY_IMG ausente no .env")
    return k


def _inline(p: Path) -> dict:
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return {"inlineData": {"mimeType": mime,
                           "data": base64.b64encode(p.read_bytes()).decode()}}


def fingerprint(prompt: str, refs: list[Path], aspect: str, image_size: str | None = None) -> str:
    h = hashlib.sha1()
    h.update(prompt.encode("utf-8"))
    h.update(aspect.encode())
    h.update(str(image_size).encode())
    for r in refs:
        h.update(r.name.encode())
        h.update(hashlib.sha1(r.read_bytes()).digest())
    return h.hexdigest()[:16]


def generate(prompt: str, out: Path, *, refs: list[Path] | None = None,
             aspect: str = "9:16", models: list[str] | None = None,
             force: bool = False, retries: int = 2,
             image_size: str | None = None, lock: bool = False) -> Path:
    """Gera `out` (png). Reaproveita se o mesmo prompt+refs ja gerou esse arquivo."""
    refs = [Path(r) for r in (refs or [])]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = out.with_suffix(".json")
    fp = fingerprint(prompt, refs, aspect, image_size)
    if not force and out.exists():
        try:
            m = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        except Exception:  # noqa: BLE001
            m = {}
        # mesmo prompt+refs -> reaproveita; "locked" (aprovada) -> nunca refaz sozinho
        if m.get("fp") == fp or m.get("locked") or not meta.exists():
            return out

    parts: list[dict] = []
    for r in refs:
        parts.append(_inline(r))
    parts.append({"text": prompt})

    last = ""
    for model in (models or DEFAULT_MODELS):
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                r = requests.post(_API.format(model=model), params={"key": _key()}, timeout=240, json={
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"responseModalities": ["IMAGE"],
                                         "imageConfig": {"aspectRatio": aspect,
                                                         **({"imageSize": image_size} if image_size else {})}},
                })
            except requests.RequestException as exc:
                last = str(exc)
                time.sleep(3)
                continue
            if r.status_code in (429, 500, 502, 503):
                last = f"{r.status_code} {r.text[:160]}"
                time.sleep(6 * (attempt + 1))
                continue
            if not r.ok:
                last = f"{r.status_code} {r.text[:300]}"
                break  # erro de requisicao/modelo -> proximo modelo
            try:
                cand = r.json()["candidates"][0]
                blob = next(p["inlineData"] for p in cand["content"]["parts"] if "inlineData" in p)
            except (KeyError, IndexError, StopIteration):
                last = f"sem imagem na resposta: {r.text[:300]}"
                continue
            out.write_bytes(base64.b64decode(blob["data"]))
            meta.write_text(json.dumps({"fp": fp, "model": model, "prompt": prompt,
                                        "refs": [x.name for x in refs], "locked": lock},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"    [gemini] {out.name} <- {model} ({time.time() - t0:.0f}s)")
            return out
        print(f"    [gemini] {model} falhou: {last}")
    raise RuntimeError(f"Gemini nao gerou {out.name}: {last}")


# ==========================================================================
# MODO BATCH (metade do preco). Usado para as cenas do episodio.
#
#  1. as referencias sobem 1x para o Files API (validas ~48h; cache local)
#  2. todas as cenas pendentes vao num unico batchGenerateContent
#  3. o estado fica em output/<ep>/_work/batch.json -> se demorar, rode o mesmo
#     comando de novo: ele so confere o lote e baixa o que ficou pronto.
# ==========================================================================
_BASE = "https://generativelanguage.googleapis.com"
_FILES_CACHE = Path(__file__).resolve().parents[1] / "output" / "gemini_files.json"


def needs(prompt: str, out: Path, refs: list[Path], aspect: str, image_size: str | None,
          force: bool) -> str | None:
    """fp se a imagem precisa ser (re)gerada; None se o cache vale."""
    fp = fingerprint(prompt, refs, aspect, image_size)
    meta = out.with_suffix(".json")
    if not force and out.exists():
        try:
            m = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        except Exception:  # noqa: BLE001
            m = {}
        if m.get("fp") == fp or m.get("locked") or not meta.exists():
            return None
    return fp


def _upload(p: Path) -> str:
    """Sobe a referencia para o Files API (com cache por conteudo)."""
    digest = hashlib.sha1(p.read_bytes()).hexdigest()
    try:
        cache = json.loads(_FILES_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cache = {}
    hit = cache.get(digest)
    if hit and time.time() - hit["t"] < 40 * 3600:
        return hit["uri"]
    data = p.read_bytes()
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    r = requests.post(f"{_BASE}/upload/v1beta/files", params={"key": _key()}, timeout=60, headers={
        "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(data)),
        "X-Goog-Upload-Header-Content-Type": mime, "Content-Type": "application/json"},
        json={"file": {"display_name": p.name}})
    r.raise_for_status()
    url = r.headers["x-goog-upload-url"]
    r = requests.post(url, timeout=300, data=data, headers={
        "Content-Length": str(len(data)), "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize"})
    r.raise_for_status()
    uri = r.json()["file"]["uri"]
    cache[digest] = {"uri": uri, "t": time.time(), "name": p.name}
    _FILES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _FILES_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return uri


def batch_submit(jobs: list[dict], state_path: Path, *, model: str = DEFAULT_MODELS[0],
                 label: str = "doramadeepweb") -> None:
    """jobs: [{key, prompt, out, refs, aspect, image_size, fp}]"""
    reqs = []
    for j in jobs:
        parts = []
        for ref in j["refs"]:
            mime = mimetypes.guess_type(Path(ref).name)[0] or "image/png"
            parts.append({"fileData": {"fileUri": _upload(Path(ref)), "mimeType": mime}})
        parts.append({"text": j["prompt"]})
        img_cfg = {"aspectRatio": j["aspect"], **({"imageSize": j["image_size"]} if j["image_size"] else {})}
        reqs.append({"request": {"contents": [{"role": "user", "parts": parts}],
                                 "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": img_cfg}},
                     "metadata": {"key": j["key"]}})
    r = requests.post(f"{_BASE}/v1beta/models/{model}:batchGenerateContent", params={"key": _key()},
                      timeout=120, json={"batch": {"display_name": label,
                                                   "input_config": {"requests": {"requests": reqs}}}})
    if not r.ok:
        raise RuntimeError(f"batch recusado: {r.status_code} {r.text[:400]}")
    name = r.json()["name"]
    state = {"name": name, "model": model, "created": time.time(),
             "jobs": [{**j, "out": str(j["out"]), "refs": [str(x) for x in j["refs"]]} for j in jobs]}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  [batch] {len(jobs)} imagem(ns) enviadas ({name}) — metade do preco")


def _responses(d: dict) -> list[dict]:
    resp = d.get("response") or {}
    inl = resp.get("inlinedResponses") or d.get("inlinedResponses") or {}
    if isinstance(inl, dict):
        inl = inl.get("inlinedResponses") or []
    return inl


def batch_poll(state_path: Path, *, wait: float = 1800, every: float = 20) -> bool:
    """Confere o lote; baixa as imagens prontas. True = terminou (estado apagado)."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    t_end = time.time() + wait
    while True:
        r = requests.get(f"{_BASE}/v1beta/{state['name']}", params={"key": _key()}, timeout=60)
        r.raise_for_status()
        d = r.json()
        st = (d.get("metadata") or {}).get("state") or d.get("state") or ""
        if st.endswith(("SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED")) or d.get("done"):
            break
        mins = (time.time() - state["created"]) / 60
        if time.time() > t_end:
            print(f"  [batch] ainda processando ({st}, {mins:.0f} min). Rode o mesmo comando depois.")
            return False
        print(f"  [batch] {st.replace('BATCH_STATE_', '').lower() or 'aguardando'}... ({mins:.0f} min)")
        time.sleep(every)
    jobs = {j["key"]: j for j in state["jobs"]}
    ok, bad = 0, []
    for i, item in enumerate(_responses(d)):
        key = ((item.get("metadata") or {}).get("key")) or state["jobs"][i]["key"]
        j = jobs.get(key)
        if not j:
            continue
        try:
            cand = item["response"]["candidates"][0]
            blob = next(p["inlineData"] for p in cand["content"]["parts"] if "inlineData" in p)
        except (KeyError, IndexError, StopIteration, TypeError):
            bad.append(f"{key}: {str(item.get('error') or item)[:160]}")
            continue
        out = Path(j["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(blob["data"]))
        out.with_suffix(".json").write_text(json.dumps(
            {"fp": j["fp"], "model": state["model"] + " (batch)", "prompt": j["prompt"],
             "refs": [Path(x).name for x in j["refs"]], "locked": False},
            ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
    print(f"  [batch] {st.replace('BATCH_STATE_', '').lower()}: {ok} imagem(ns) prontas"
          + (f", {len(bad)} falharam" if bad else ""))
    for b in bad:
        print(f"    !! {b}")
    state_path.unlink(missing_ok=True)
    return True
