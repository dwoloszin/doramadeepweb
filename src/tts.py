"""Narracao com tempo por palavra (legenda sincronizada).

Voz principal: ElevenLabs eleven_v3 (src/elevenlabs.py), com marcacoes de
atuacao no roteiro ([whispers], [excited]...). As falas SEGUIDAS da mesma
pessoa numa cena saem numa chamada so — a entonacao continua de uma frase pra
outra, como um ator lendo o paragrafo — e depois o audio e cortado por fala.

Reserva: edge-tts (sem marcacoes), se nenhuma chave do ElevenLabs funcionar.
Tudo fica em cache (hash do texto + voz); `retake` refaz uma cena.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import edge_tts

from . import elevenlabs, ffmpeg

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:  # noqa: BLE001
        pass

TICKS = 10_000_000


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Line:
    who: str
    text: str
    audio: Path
    duration: float
    words: list[Word]
    tr: str = ""


async def _synth(text: str, out: Path, v: dict) -> list[Word]:
    com = edge_tts.Communicate(text, voice=v["voice"], rate=v.get("rate", "+0%"),
                               pitch=v.get("pitch", "+0Hz"), volume=v.get("volume", "+0%"),
                               boundary="WordBoundary")
    words: list[Word] = []
    with open(out, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / TICKS
                words.append(Word(ch["text"], s, s + ch["duration"] / TICKS))
    return words


def _norm(t: str) -> str:
    return re.sub(r"[^\wÀ-ÿ']", "", t.lower())


def _restore_punctuation(text: str, words: list[Word]) -> list[Word]:
    """Troca o texto cru de cada palavra pelo token original (com pontuacao)."""
    tokens = [t for t in text.split() if _norm(t)]
    if len(tokens) == len(words):
        return [Word(tok, w.start, w.end) for tok, w in zip(tokens, words)]
    # desalinhado (contracoes, numeros): casa pelo texto normalizado, em ordem
    out, j = [], 0
    for w in words:
        nw = _norm(w.text)
        k = j
        while k < len(tokens) and _norm(tokens[k]) != nw and k - j < 3:
            k += 1
        if k < len(tokens) and _norm(tokens[k]) == nw:
            out.append(Word(tokens[k], w.start, w.end))
            j = k + 1
        else:
            out.append(w)
    return out


def _lufs(path: Path) -> float | None:
    import subprocess
    r = subprocess.run([ffmpeg.ffmpeg_exe(), "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


# Voz de pensamento = a MESMA voz do narrador, tratada para soar "dentro da cabeca".
#  thought       (padrao desde 12/11): intima e proxima — compressao suave, presenca, so um
#                toque de ambiencia curta (o usuario achou o eco antigo "estranho")
#  thought_echo  a versao antiga do ep01 (eco forte e abafado)
THOUGHT_FX = {
    "thought": ("highpass=f=90,lowpass=f=9500,acompressor=threshold=0.125:ratio=2:attack=10:release=120,"
                "equalizer=f=3000:t=q:w=1.2:g=2,aecho=0.8:0.3:18|34:0.10|0.05,apad=pad_dur=0.2"),
    # leve: quase cru, so um toque de ambiencia (preserva emocao e energia)
    "thought_light": "highpass=f=80,aecho=0.8:0.25:15|30:0.08|0.04,apad=pad_dur=0.15",
    "thought_echo": "highpass=f=120,lowpass=f=7500,aecho=0.9:0.7:45|90:0.28|0.15,apad=pad_dur=0.25",
    # mais grave/encorpado (Ep. 7+, "mais HOMEM"): ~1 semitom abaixo, sem mudar o andamento,
    # graves reforcados. Mesma voz (Liam), so mais peso.
    "thought_deep": ("aresample=44100,asetrate=44100*0.944,aresample=44100,atempo=1.0593,"
                     "highpass=f=60,equalizer=f=140:t=q:w=1:g=3,equalizer=f=4500:t=q:w=1.5:g=-2,"
                     "aecho=0.8:0.25:15|30:0.08|0.04,apad=pad_dur=0.15"),
    # meio-termo (12/11: thought_deep ficou "muito grossa"): ~meio semitom, grave sutil — natural
    "thought_mid": ("aresample=44100,asetrate=44100*0.972,aresample=44100,atempo=1.0288,"
                    "highpass=f=70,equalizer=f=150:t=q:w=1:g=1.5,"
                    "aecho=0.8:0.25:15|30:0.08|0.04,apad=pad_dur=0.15"),
    "mid_dry": ("aresample=44100,asetrate=44100*0.972,aresample=44100,atempo=1.0288,"
                "highpass=f=70,equalizer=f=150:t=q:w=1:g=1.5"),
    # fala em VOZ ALTA do Davi (Ep. 7+): mesmo grave do thought_deep, sem ambiencia de pensamento
    "deep_dry": ("aresample=44100,asetrate=44100*0.944,aresample=44100,atempo=1.0593,"
                 "highpass=f=60,equalizer=f=140:t=q:w=1:g=3,equalizer=f=4500:t=q:w=1.5:g=-2"),
    # voz do outro lado da LINHA TELEFONICA (Ep. 12): banda estreita de telefone fixo + leve saturacao
    "phone": ("highpass=f=320,lowpass=f=3300,equalizer=f=1800:t=q:w=1:g=4,"
              "acompressor=threshold=0.1:ratio=4:attack=5:release=60,volume=1.4"),
    "thought_deep2": ("aresample=44100,asetrate=44100*0.91,aresample=44100,atempo=1.0989,"
                      "highpass=f=55,equalizer=f=130:t=q:w=1:g=4,equalizer=f=4500:t=q:w=1.5:g=-3,"
                      "aecho=0.8:0.25:15|30:0.08|0.04,apad=pad_dur=0.15"),
}


def _apply_fx(src: Path, fx: str, tempo: float = 1.0, level: float | None = None) -> Path:
    """Andamento + efeito de pensamento + NIVEL igual para todas as falas.

    `level` (LUFS) iguala o volume de cada fala: o v3 entrega umas tomadas bem
    mais baixas (sussurros), e o pensamento chegou a ficar 19 dB abaixo do
    narrador."""
    chain = []
    if abs(tempo - 1.0) > 1e-3:
        chain.append(f"atempo={tempo:.4f}")
    if fx in THOUGHT_FX:
        chain.append(THOUGHT_FX[fx])
    if not chain and level is None:
        return src
    tag = hashlib.sha1((",".join(chain) + f"|{level}").encode()).hexdigest()[:6]
    out = src.with_name(f"{src.stem}_fx{tag}.mp3")
    if out.exists():
        return out
    if level is not None:
        tmp = src.with_name(f"{src.stem}_tmp{tag}.wav")
        ffmpeg.run(["-i", str(src), *(["-af", ",".join(chain)] if chain else []), str(tmp)])
        cur = _lufs(tmp)
        gain = 0.0 if cur is None or cur < -70 else max(-12.0, min(24.0, level - cur))
        ffmpeg.run(["-i", str(tmp), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.89:level=false",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(out)])
        tmp.unlink(missing_ok=True)
    else:
        ffmpeg.run(["-i", str(src), "-af", ",".join(chain), "-c:a", "libmp3lame", "-b:a", "192k", str(out)])
    return out


def synth_line(who: str, text: str, voices: dict, cache: Path, tr: str = "") -> Line:
    """edge-tts (reserva). Marcacoes [..] sao removidas."""
    text = elevenlabs.strip_tags(text)
    v = voices[who]
    key = hashlib.sha1(json.dumps([text, v], sort_keys=True).encode()).hexdigest()[:14]
    cache.mkdir(parents=True, exist_ok=True)
    mp3 = cache / f"{who}_{key}.mp3"
    meta = mp3.with_suffix(".json")
    if mp3.exists() and meta.exists():
        words = [Word(**w) for w in json.loads(meta.read_text(encoding="utf-8"))]
    else:
        words, err = [], None
        for attempt in range(4):
            try:
                words = asyncio.run(_synth(text, mp3, v))
                break
            except Exception as exc:  # noqa: BLE001  (o servico do edge falha as vezes)
                err = exc
                import time
                time.sleep(2 + 3 * attempt)
        if err and not words:
            raise RuntimeError(f"edge-tts falhou ({who}: {text!r}): {err}")
        if not words:
            raise RuntimeError(f"edge-tts nao devolveu tempos para: {text}")
        words = _restore_punctuation(text, words)
        meta.write_text(json.dumps([asdict(w) for w in words], ensure_ascii=False), encoding="utf-8")
    audio = _apply_fx(mp3, v.get("fx", ""))
    # duracao "falada" (fim da ultima palavra): o silencio que o edge-tts poe no
    # fim do arquivo nao conta, senao as pausas do roteiro viram buracos.
    dur = words[-1].end + 0.12
    return Line(who, text, audio, dur, words, tr)


# --------------------------------------------------------------------------
# ElevenLabs: uma chamada por bloco de falas seguidas da mesma pessoa
# --------------------------------------------------------------------------
def _keeps(t0: float, t1: float, wl: list, max_gap: float) -> list[tuple[float, float]]:
    """Trechos a manter: tira o miolo dos silencios maiores que max_gap."""
    keeps, cur = [], t0
    for a, b in zip(wl, wl[1:]):
        gap = b[1] - a[2]
        if max_gap > 0 and gap > max_gap:
            keeps.append((cur, a[2] + max_gap / 2))
            cur = b[1] - max_gap / 2
    keeps.append((cur, t1))
    return keeps


def _remap(t: float, keeps: list[tuple[float, float]]) -> float:
    out = 0.0
    for a, b in keeps:
        if t <= b:
            return out + max(0.0, t - a)
        out += b - a
    return out


def _cut(src: Path, out: Path, keeps: list[tuple[float, float]]) -> None:
    parts = "".join(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[p{i}];" for i, (a, b) in enumerate(keeps))
    cat = "".join(f"[p{i}]" for i in range(len(keeps)))
    fc = (f"{parts}{cat}concat=n={len(keeps)}:v=0:a=1,"
          "afade=t=in:d=0.02,areverse,afade=t=in:d=0.04,areverse[o]")
    ffmpeg.run(["-i", str(src), "-filter_complex", fc, "-map", "[o]",
                "-c:a", "libmp3lame", "-b:a", "192k", str(out)])


def _eleven_group(who: str, texts: list[str], v: dict, model: str, cache: Path,
                  force: bool, max_gap: float = 0.45) -> list[tuple[Path, list[Word]]]:
    joined = " ".join(t.strip() for t in texts)
    key = hashlib.sha1(json.dumps([joined, v.get("eleven"), model], sort_keys=True).encode()).hexdigest()[:14]
    raw, meta = cache / f"11_{who}_{key}.mp3", cache / f"11_{who}_{key}.json"
    if force or not (raw.exists() and meta.exists()):
        print(f"    [voz] {who}: {elevenlabs.strip_tags(joined)[:70]}...")
        ws = elevenlabs.synthesize(joined, raw, v, model)
        meta.write_text(json.dumps(ws, ensure_ascii=False), encoding="utf-8")
    ws = [tuple(w) for w in json.loads(meta.read_text(encoding="utf-8"))]
    # a que fala pertence cada palavra (pela posicao do caractere no texto unido)
    bounds, pos = [], 0
    for t in texts:
        t = t.strip()
        bounds.append((pos, pos + len(t)))
        pos += len(t) + 1
    per = [[w for w in ws if b0 <= w[3] < b1] for (b0, b1) in bounds]
    total = ffmpeg.probe_duration(raw)
    out = []
    for i, wl in enumerate(per):
        if not wl:
            raise RuntimeError(f"fala sem palavras no alinhamento: {texts[i]!r}")
        prev_end = per[i - 1][-1][2] if i > 0 else 0.0
        next_start = per[i + 1][0][1] if i + 1 < len(per) else total
        t0 = max(prev_end + (wl[0][1] - prev_end) * 0.5, wl[0][1] - 0.12, 0.0)
        t1 = min(wl[-1][2] + (next_start - wl[-1][2]) * 0.5, wl[-1][2] + 0.35, total)
        keeps = _keeps(t0, t1, wl, max_gap)
        seg = cache / f"11_{who}_{key}_{i}_g{int(max_gap * 100)}.mp3"
        if force or not seg.exists():
            _cut(raw, seg, keeps)
        out.append((seg, [Word(w[0], _remap(w[1], keeps), _remap(w[2], keeps)) for w in wl]))
    return out


def synth_shot(lines: list[dict], voices: dict, cache: Path, *, model: str = "eleven_v3",
               provider: str = "elevenlabs", force: bool = False, max_gap: float = 0.45) -> list[Line]:
    """Todas as falas de uma cena -> Line (na mesma ordem)."""
    cache.mkdir(parents=True, exist_ok=True)
    result: list[Line | None] = [None] * len(lines)
    i = 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and lines[j + 1]["who"] == lines[i]["who"]:
            j += 1
        who, group = lines[i]["who"], lines[i:j + 1]
        v = voices[who]
        tempo = float(v.get("tempo", 1.0))
        pieces = None
        if provider == "elevenlabs" and v.get("eleven"):
            try:
                pieces = _eleven_group(who, [g["text"] for g in group], v, model, cache, force, max_gap)
            except elevenlabs.Unavailable as exc:
                print(f"  !! ElevenLabs indisponivel ({exc}) — usando voz RESERVA (edge-tts)")
        for k, g in enumerate(group):
            if pieces is None:
                result[i + k] = synth_line(who, g["text"], voices, cache, tr=g.get("tr", ""))
                continue
            seg, words = pieces[k]
            lvl = v.get("level_lufs", -18.0)
            audio = _apply_fx(seg, v.get("fx", ""), tempo, None if lvl is None else float(lvl))
            words = [Word(w.text, w.start / tempo, w.end / tempo) for w in words]
            words = _restore_punctuation(elevenlabs.strip_tags(g["text"]), words)
            result[i + k] = Line(who, elevenlabs.strip_tags(g["text"]), audio,
                                 words[-1].end + 0.12, words, g.get("tr", ""))
        i = j + 1
    return result  # type: ignore[return-value]
