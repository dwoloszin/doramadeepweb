"""Hashtags EXTRA da vez (teste de alcance), somadas as do episodio — nunca substituem o basico.

config.yaml -> hashtags: {tagset, extra_hashtags, extra_tags}
  * extra_hashtags: entram no fim da linha de hashtags de descricao/legenda (YouTube, Instagram, TikTok)
  * extra_tags:     tags invisiveis do YouTube (o que as pessoas digitam na busca)
  * tagset:         nome do teste -> gravado no status.json e comparado em output/METRICAS.md
"""
from __future__ import annotations

from .config import load_config


def _cfg(key: str, default):
    try:
        return load_config().get(f"hashtags.{key}", default) or default
    except Exception:  # noqa: BLE001
        return default


def tagset() -> str:
    return str(_cfg("tagset", "base"))


def add(text: str) -> str:
    """Acrescenta as hashtags extra (sem repetir) na ultima linha de hashtags, ou numa linha nova."""
    extra = [h for h in _cfg("extra_hashtags", []) if h.lower() not in (text or "").lower()]
    if not extra:
        return text
    lines = (text or "").rstrip().split("\n")
    if lines and lines[-1].strip().startswith("#"):
        lines[-1] = lines[-1].rstrip() + " " + " ".join(extra)
    else:
        lines += ["", " ".join(extra)]
    return "\n".join(lines)


def tags(base: list) -> list:
    out, seen = [], set()
    for t in list(base or []) + list(_cfg("extra_tags", [])):
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    while out and len(",".join(out)) > 480:   # limite do YouTube (~500 caracteres)
        out.pop(-1 - len(_cfg("extra_tags", [])) if len(out) > len(_cfg("extra_tags", [])) else -1)
    return out


def tiktok(text: str) -> str:
    """TikTok funciona como buscador: palavras-chave NA legenda + hashtags extra so do TikTok."""
    lead = _cfg("tiktok_lead", "")
    t = text or ""
    if lead:
        for old in ("📖 Baseado em fatos reais.", "📖 Baseado em fatos reais"):
            if old in t:
                t = t.replace(old, lead, 1)
                break
    t = add(t)
    extra = [h for h in _cfg("tiktok_extra_hashtags", []) if h.lower() not in t.lower()]
    if extra:
        lines = t.rstrip().split("\n")
        lines[-1] = lines[-1].rstrip() + " " + " ".join(extra)
        t = "\n".join(lines)
    return t
