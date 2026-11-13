"""Legendas .ass (queimadas no video) e .srt (closed caption do YouTube).

Tres estilos, como em filme:
  Narr    narrador — Poppins, branco, palavra falada em dourado
  Thought pensamento — Lora italico, lilas, entre aspas suaves
  Dialog  fala de personagem — Cormorant italico grande + traducao embaixo
"""
from __future__ import annotations

from pathlib import Path

from .config import Config


def _t(s: float) -> str:
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("{", "(").replace("}", ")").replace("\n", " ")


def _groups(words, max_chars: int, pause: float = 0.38):
    """Quebra em frases (pontuacao/pausa) e depois em blocos de ate max_chars."""
    phrases, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (w.text.endswith((".", "!", "?", "…", ";", ":")) or
                (w.text.endswith(",") and sum(len(x.text) + 1 for x in cur) > max_chars * 0.6) or
                (nxt and nxt.start - w.end > pause) or nxt is None):
            phrases.append(cur)
            cur = []
    out = []
    for ph in phrases:
        total = sum(len(w.text) + 1 for w in ph)
        n = max(1, -(-total // max_chars))
        target = total / n
        g, acc = [], 0
        for w in ph:
            if g and acc + len(w.text) > target * 1.15 and len(out) >= 0:
                out.append(g)
                g, acc = [], 0
            g.append(w)
            acc += len(w.text) + 1
        if g:
            # nunca deixa uma palavra sozinha no fim
            if len(g) == 1 and out and out[-1] and out[-1][0] in ph:
                out[-1].append(g[0])
            else:
                out.append(g)
    return out


def build_ass(timeline: list[dict], cfg: Config, out: Path, width: int, height: int) -> Path:
    """timeline: [{who, words(abs times), tr}]"""
    size = int(cfg.get("subtitles.size", 64))
    mv = int(cfg.get("subtitles.margin_v", 470))
    hi = cfg.get("subtitles.highlight", "&H0070D7FF")
    th_col = cfg.get("subtitles.thought_color", "&H00F5D8E6")
    max_chars = int(cfg.get("subtitles.max_chars", 30))
    f_narr = cfg.get("subtitles.font", "Poppins SemiBold")
    f_th = cfg.get("subtitles.thought_font", "Lora Italic")
    f_dl = cfg.get("subtitles.dialogue_font", "Cormorant SemiBold Italic")
    ml = 80
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding")
    # sombra difusa (outline grosso, preto translucido + blur) = leitura em qualquer fundo, sem caixa
    styles = [
        f"Style: Narr,{f_narr},{size},&H00FFFFFF,&H00FFFFFF,&H90000000,&HA0000000,0,0,0,0,100,100,0.5,0,1,5,2,2,{ml},{ml},{mv},1",
        f"Style: Thought,{f_th},{int(size * 1.02)},{th_col},{th_col},&H90100018,&HA0000000,0,0,0,0,100,100,0,0,1,5,2,2,{ml},{ml},{mv},1",
        f"Style: Dialog,{f_dl},{int(size * 1.15)},&H00FFFFFF,&H00FFFFFF,&H90000000,&HA0000000,0,0,0,0,100,100,0,0,1,5,2,2,{ml},{ml},{mv + 50},1",
        f"Style: Tr,{f_narr},{int(size * 0.6)},&H00C8E6F0,&H00C8E6F0,&H90000000,&HA0000000,0,0,0,0,100,100,0.5,0,1,4,1,2,{ml},{ml},{mv - 70},1",
    ]
    ev: list[str] = []
    for item in timeline:
        if item.get("card"):
            continue  # cartela ja mostra o texto na tela
        who, words = item["who"], item["words"]
        style = {"narrador": "Narr", "pensamento": "Thought"}.get(who, "Dialog")
        groups = _groups(words, int(max_chars * (1.6 if style == "Dialog" else 1.8)))
        for g in groups:
            g_start, g_end = g[0].start, g[-1].end + 0.18
            for k, w in enumerate(g):
                s = g_start if k == 0 else w.start
                e = g[k + 1].start if k + 1 < len(g) else g_end
                parts = []
                for j, x in enumerate(g):
                    t = _esc(x.text)
                    if style == "Thought" and j == 0:
                        t = "“" + t
                    if style == "Thought" and j == len(g) - 1 and g is groups[-1]:
                        t = t + "”"
                    parts.append(("{\\c" + hi + "&}" + t + "{\\r}") if j == k and style != "Thought" else
                                 ("{\\alpha&H00&}" + t) if j <= k else ("{\\alpha&H30&}" + t))
                txt = "{\\blur3}" + " ".join(parts)
                if k == 0:
                    txt = "{\\fad(120,0)}" + txt
                ev.append(f"Dialogue: 0,{_t(s)},{_t(e)},{style},,0,0,0,,{txt}")
        if item.get("tr"):
            ev.append(f"Dialogue: 0,{_t(words[0].start)},{_t(words[-1].end + 0.6)},Tr,,0,0,0,,"
                      f"{{\\fad(200,200)\\blur2}}{_esc(item['tr'])}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n" + fmt + "\n" + "\n".join(styles) + "\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(ev) + "\n", encoding="utf-8")
    return out


def build_srt(timeline: list[dict], out: Path, max_chars: int = 42) -> Path:
    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    cues = []
    for item in timeline:
        for g in _groups(item["words"], max_chars):
            text = " ".join(w.text for w in g)
            if item["who"] == "pensamento":
                text = f"<i>{text}</i>"
            cues.append([g[0].start, g[-1].end + 0.15, text])
        if item.get("tr"):
            end = item["words"][-1].end
            cues.append([end + 0.16, end + 2.2, f"({item['tr']})"])
    cues.sort(key=lambda c: c[0])
    rows = []
    for n, c in enumerate(cues):
        if n + 1 < len(cues):  # uma legenda nao invade a proxima
            c[1] = min(c[1], cues[n + 1][0] - 0.02)
        rows += [str(n + 1), f"{ts(c[0])} --> {ts(c[1])}", c[2], ""]
    out.write_text("\n".join(rows), encoding="utf-8")
    return out
