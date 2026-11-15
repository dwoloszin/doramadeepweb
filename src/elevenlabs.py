"""ElevenLabs (eleven_v3) — voz humanizada com direcao de atuacao.

Mesmo esquema do ubt-bemnamosca:
  * ELEVENLABS_API_KEYS no .env (varias chaves gratuitas, separadas por virgula);
  * antes de cada fala consulta o saldo da chave e roda para a proxima quando acaba;
  * chave esgotada/invalida fica anotada em output/elevenlabs_state.json (30 dias);
  * /with-timestamps devolve o tempo de cada letra -> legenda sincronizada.

Novidade aqui: o roteiro pode ter MARCACOES DE ATUACAO entre colchetes, que o
eleven_v3 interpreta e nao fala: [whispers] [excited] [sighs] [laughs softly]
[nervous] [dramatic] ... Elas somem das palavras (legenda/srt).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

from .config import ROOT

API = "https://api.elevenlabs.io/v1"
_COST = {"eleven_turbo_v2_5": 0.5, "eleven_flash_v2_5": 0.5}  # resto: 1 credito/caractere
_EXHAUST_DAYS = 30
TAG_RE = re.compile(r"\[[^\]]*\]")


class Unavailable(RuntimeError):
    """Nenhuma chave conseguiu sintetizar (o chamador cai no edge-tts)."""


# --------------------------------------------------------------------------
# LIMITE MENSAL DO DORAMA (14/11): as chaves sao COMPARTILHADAS com o bemnamosca e o canal
# de GTA. O Dorama so pode gastar `tts.monthly_cap` creditos por mes (config.yaml); o gasto
# fica em output/voz_uso.json (versionado: vale local e no GitHub Actions).
# --------------------------------------------------------------------------
USAGE = ROOT / "output" / "voz_uso.json"


class OverCap(RuntimeError):
    """Limite mensal do Dorama atingido — NAO cai na voz reserva: espera o mes seguinte."""


def _month() -> str:
    return time.strftime("%Y-%m")


def monthly_cap() -> float:
    try:
        from .config import load_config
        return float(load_config().get("tts.monthly_cap", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def used(month: str | None = None) -> float:
    try:
        return float(json.loads(USAGE.read_text(encoding="utf-8")).get(month or _month(), 0))
    except Exception:  # noqa: BLE001
        return 0.0


def allowance() -> float:
    """Quanto o Dorama ainda pode gastar neste mes (inf = sem limite)."""
    cap = monthly_cap()
    return max(0.0, cap - used()) if cap else float("inf")


def _check(cost: float) -> None:
    if cost > allowance():
        raise OverCap(f"limite mensal de voz do Dorama atingido ({used():.0f}/{monthly_cap():.0f} em {_month()}); "
                      "as chaves sao compartilhadas com os outros canais — espera o proximo mes")


def _spend(cost: float) -> None:
    try:
        d = json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    except Exception:  # noqa: BLE001
        d = {}
    d[_month()] = round(float(d.get(_month(), 0)) + cost, 1)
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    USAGE.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _tts_cfg(key: str, default):
    try:
        from .config import load_config
        v = load_config().get(f"tts.{key}", default)
        return default if v is None else v
    except Exception:  # noqa: BLE001
        return default


def reserved() -> list[str]:
    """Finais (4 ultimos caracteres) das chaves que o Dorama NAO usa (reservadas a outro projeto)."""
    return [str(x)[-4:] for x in (_tts_cfg("reserved_keys", []) or [])]


def key_min() -> float:
    """So usa uma chave se, DEPOIS da fala, ainda sobrar pelo menos isto (folga p/ os outros canais)."""
    return float(_tts_cfg("key_min_credits", 500))


def pool_credits() -> tuple[float, list[tuple[str, float]]]:
    """Consulta o saldo de cada chave utilizavel -> (total aproveitavel, [(final, saldo)])."""
    p, rows, tot = _Pool(), [], 0.0
    for k in p.usable():
        c = p.credits(k)
        c = 0.0 if c is None else c
        rows.append((k[-4:], c))
        tot += max(0.0, c - key_min())
    return tot, rows


def estimate(epd: dict) -> float:
    """Creditos de voz que o episodio vai gastar (falas + efeitos novos ~40/s)."""
    need = sum(len(strip_tags(ln.get("text", ""))) for sh in epd["shots"] for ln in sh.get("lines") or [])
    need += 40 * sum(float(x.get("dur", 3)) for sh in epd["shots"] for x in (sh.get("sfx") or [])
                     if isinstance(x, dict) and x.get("gen"))
    return float(need)


def preflight(need: float, what: str = "") -> tuple[bool, str]:
    """ANTES de chamar a API: tem credito de sobra (chaves + limite mensal) para `need`? (margem 30%)"""
    have, _ = pool_credits()
    cap_left = allowance()
    ok = min(have, cap_left) >= need * 1.3
    msg = (f"{what} precisa ~{need:.0f} creditos (+30% de folga); chaves: {have:.0f} aproveitaveis "
           f"(acima do minimo de {key_min():.0f} por chave); limite mensal do Dorama: "
           f"{'sem limite' if cap_left == float('inf') else f'{cap_left:.0f} restantes'}")
    return ok, msg


def strip_tags(text: str) -> str:
    return re.sub(r"\s{2,}", " ", TAG_RE.sub(" ", text)).strip()


def _kid(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()[:12]


class _Pool:
    def __init__(self) -> None:
        raw = os.getenv("ELEVENLABS_API_KEYS", "") or os.getenv("ELEVENLABS_API_KEY", "")
        res = reserved()   # chaves reservadas a outro projeto: o Dorama nem enxerga
        self.keys = [k for k in re.split(r"[,;\s]+", raw) if k.startswith("sk_") and k[-4:] not in res]
        self.path = ROOT / "output" / "elevenlabs_state.json"
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self.state = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def usable(self) -> list[str]:
        now, out = time.time(), []
        for k in self.keys:
            st = self.state.get(_kid(k), {})
            if st.get("invalid") or (st.get("exhausted_at") and now - st["exhausted_at"] < _EXHAUST_DAYS * 86400):
                continue
            out.append(k)
        return out

    def mark(self, k: str, what: str) -> None:
        self.state.setdefault(_kid(k), {})[what] = time.time() if what == "exhausted_at" else True
        self._save()

    @staticmethod
    def credits(k: str) -> float | None:
        try:
            r = requests.get(f"{API}/user/subscription", headers={"xi-api-key": k}, timeout=15)
            if r.ok:
                d = r.json()
                return float(d.get("character_limit", 0)) - float(d.get("character_count", 0))
        except Exception:  # noqa: BLE001
            pass
        return None


def available() -> bool:
    return bool(_Pool().usable())


def status() -> str:
    p = _Pool()
    rows = []
    for k in p.keys:
        c = p.credits(k)
        rows.append(f"  ...{k[-4:]}: {'?' if c is None else int(c)} creditos")
    return "\n".join(rows) or "  (nenhuma chave em ELEVENLABS_API_KEYS)"


def words_from_alignment(text: str, al: dict) -> tuple[list[tuple[str, float, float, int]], list[float]]:
    """Palavras (texto, inicio, fim, indice_char) sem as marcacoes [..].

    Devolve tambem a duracao de cada marcacao — se passar de ~0.6s a voz
    provavelmente LEU a marcacao em voz alta (aviso para refazer)."""
    starts = al.get("character_start_times_seconds") or []
    ends = al.get("character_end_times_seconds") or []
    chars = "".join(al.get("characters") or [])
    src = chars if len(chars) == len(starts) else text
    masked = list(src)
    tag_durs = []
    for m in TAG_RE.finditer(src):
        for i in range(m.start(), m.end()):
            masked[i] = " "
        if m.end() - 1 < len(ends):
            tag_durs.append(ends[m.end() - 1] - starts[m.start()])
    words = []
    for m in re.finditer(r"\S+", "".join(masked)):
        s, e = m.start(), m.end() - 1
        if e < len(ends):
            words.append((m.group(0), float(starts[s]), float(ends[e]), s))
    return words, tag_durs


def synthesize(text: str, out: Path, v: dict, model: str) -> list[tuple[str, float, float, int]]:
    """Gera `out` (mp3) e devolve as palavras com tempos. Levanta Unavailable."""
    pool = _Pool()
    keys = pool.usable()
    if not keys:
        raise Unavailable("sem chaves ElevenLabs utilizaveis (ELEVENLABS_API_KEYS)")
    e = v["eleven"]
    voice_id = e["voice_id"]
    cost = len(text) * _COST.get(model, 1.0)
    _check(cost)
    body = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": float(e.get("stability", 0.5)),
            "similarity_boost": float(e.get("similarity", 0.8)),
            "style": float(e.get("style", 0.0)),
            "use_speaker_boost": True,
        },
    }
    if e.get("lang"):
        body["language_code"] = e["lang"]
    if e.get("seed") is not None:
        body["seed"] = int(e["seed"])
    last = None
    for k in keys:
        c = pool.credits(k)
        if c is None or c < cost + key_min():   # sem consulta OK ou pouco credito: nao chama
            print(f"    [11labs] chave ...{k[-4:]} com {c:.0f} creditos (precisa ~{cost:.0f}) — proxima")
            if c is not None and c < 300:
                pool.mark(k, "exhausted_at")
            continue
        for attempt in range(3):
            try:
                r = requests.post(f"{API}/text-to-speech/{voice_id}/with-timestamps",
                                  params={"output_format": "mp3_44100_128"},
                                  headers={"xi-api-key": k, "Content-Type": "application/json"},
                                  json=body, timeout=180)
            except requests.RequestException as exc:
                last = exc
                time.sleep(2 + 3 * attempt)
                continue
            if r.status_code == 401:
                pool.mark(k, "invalid")
                break
            if r.status_code in (402, 403) and any(x in r.text for x in ("paid_plan_required", "voice_access_denied",
                                                                       "voice_disabled", "missing_permissions")):
                # problema da VOZ/permissao, nao de credito: nao queimar a chave
                raise RuntimeError(f"ElevenLabs recusou (voz/permissao, chave preservada): {r.text[:200]}")
            if r.status_code in (402, 429) or (r.status_code == 400 and "quota" in r.text.lower()):
                if r.status_code == 429 and "concurrent" in r.text.lower():
                    time.sleep(4)
                    continue
                pool.mark(k, "exhausted_at")
                break
            if r.status_code >= 500:
                last = RuntimeError(f"{r.status_code} {r.text[:120]}")
                time.sleep(3 + 3 * attempt)
                continue
            if not r.ok:
                raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
            d = r.json()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(d["audio_base64"]))
            words, tag_durs = words_from_alignment(text, d.get("alignment") or {})
            if not words:
                raise RuntimeError("ElevenLabs sem alinhamento de palavras")
            if any(t > 0.6 for t in tag_durs) and not re.search(r"sigh|laugh|chuckle|exhale|gasp", text):
                print(f"    [11labs] AVISO: uma marcacao pode ter sido falada: {text[:60]!r}")
            _spend(cost)
            return words
    raise Unavailable(f"nenhuma chave ElevenLabs funcionou (ultimo erro: {last})")


# --------------------------------------------------------------------------
# efeitos sonoros / ambiente (Sound Effects API)
# --------------------------------------------------------------------------
SFX_DIR = ROOT / "assets" / "sfx" / "gen"


def sound(prompt: str, *, duration: float | None = None, loop: bool = False,
          influence: float = 0.45) -> Path:
    """Gera (uma vez) um efeito/ambiente e devolve o mp3 em cache.

    O cache fica em assets/sfx/gen/ e vale para todos os episodios: o mesmo
    lugar soa sempre igual (continuidade de som, como a de imagem)."""
    body = {"text": prompt, "prompt_influence": influence}
    if duration:
        body["duration_seconds"] = max(0.5, min(22.0, float(duration)))
    if loop:
        body["loop"] = True
    h = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower())[:40].strip("_")
    out = SFX_DIR / f"{slug}_{h}.mp3"
    if out.exists():
        return out
    sfx_cost = 40.0 * float(body.get("duration_seconds", 5.0))   # efeito: ~40 creditos/segundo
    _check(sfx_cost)
    pool = _Pool()
    last = None
    for k in pool.usable():
        c = pool.credits(k)     # consulta ANTES de chamar
        if c is None or c < sfx_cost + key_min():
            continue
        for attempt in range(3):
            try:
                r = requests.post(f"{API}/sound-generation", headers={"xi-api-key": k}, json=body, timeout=180)
            except requests.RequestException as exc:
                last = exc
                time.sleep(2 + 3 * attempt)
                continue
            if r.status_code == 401:
                pool.mark(k, "invalid")
                break
            if r.status_code in (402, 403) and any(x in r.text for x in ("paid_plan_required", "voice_access_denied",
                                                                       "voice_disabled", "missing_permissions")):
                # problema da VOZ/permissao, nao de credito: nao queimar a chave
                raise RuntimeError(f"ElevenLabs recusou (voz/permissao, chave preservada): {r.text[:200]}")
            if r.status_code in (402, 429) or (r.status_code == 400 and "quota" in r.text.lower()):
                if r.status_code == 429 and "concurrent" in r.text.lower():
                    time.sleep(4)
                    continue
                pool.mark(k, "exhausted_at")
                break
            if r.status_code >= 500:
                last = RuntimeError(f"{r.status_code} {r.text[:120]}")
                time.sleep(3 + 3 * attempt)
                continue
            if not r.ok:
                raise RuntimeError(f"ElevenLabs SFX {r.status_code}: {r.text[:300]}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.content)
            _spend(sfx_cost)
            out.with_suffix(".json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"    [som] gerado: {prompt[:60]}")
            return out
    raise Unavailable(f"efeito nao gerado ({prompt[:40]}): {last}")
