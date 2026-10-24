"""Gera o arquivo .ass de legendas sincronizado com a narração, com vários estilos."""

from pathlib import Path
from typing import Dict, List

# Cores ASS em BGR: &HAABBGGRR. "hl" = cor da palavra destacada.
STYLES: Dict[str, Dict] = {
    "classico": {"label": "Clássico", "mode": "block", "font": "Arial Black", "scale": 1.0,
                 "primary": "&H00FFFFFF", "outline_color": "&H00000000", "outline": 6, "shadow": 2, "border": 1},
    "karaoke": {"label": "Karaokê", "mode": "karaoke", "font": "Arial Black", "scale": 1.0,
                "primary": "&H00FFFFFF", "hl": "&H0000E5FF", "outline_color": "&H00000000", "outline": 6, "shadow": 2, "border": 1},
    "pop": {"label": "Pop (palavra a palavra)", "mode": "word", "font": "Arial Black", "scale": 1.3,
            "primary": "&H0000E5FF", "outline_color": "&H00000000", "outline": 8, "shadow": 3, "border": 1},
    "caixa": {"label": "Caixa", "mode": "block", "font": "Arial", "scale": 0.9,
              "primary": "&H00FFFFFF", "outline_color": "&H00101010", "outline": 14, "shadow": 0, "border": 3},
    "neon": {"label": "Neon", "mode": "block", "font": "Arial Black", "scale": 1.0,
             "primary": "&H00FFFF00", "outline_color": "&H00B4005A", "outline": 5, "shadow": 0, "border": 1, "glow": True},
    "minimalista": {"label": "Minimalista", "mode": "block", "font": "Arial", "scale": 0.8,
                    "primary": "&H00FFFFFF", "outline_color": "&H00000000", "outline": 3, "shadow": 1, "border": 1},
}
DEFAULT_STYLE = "classico"

_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary},&H000000FF,{outline_color},&H64000000,-1,0,0,0,100,100,0,0,{border},{outline},{shadow},2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def _escape_token(token: str) -> str:
    """Neutraliza o que o ASS interpreta como comando (\\, {, })."""
    return token.replace("\\", "/").replace("{", "(").replace("}", ")")


def _tag_color(ass_color: str) -> str:
    return "&H" + ass_color[-6:] + "&"


def _token_times(segment: Dict, tokens: List[str]) -> List[tuple]:
    """Tempo (início, fim) relativo de cada token: WordBoundary do Edge TTS ou proporcional."""
    duration = segment["duration"]
    words = segment.get("words") or []
    if len(words) == len(tokens) and tokens:
        scale = duration / words[-1]["end"] if words[-1]["end"] > duration else 1.0
        return [(w["start"] * scale, min(duration, w["end"] * scale)) for w in words]
    total = sum(len(t) for t in tokens) or 1
    times, cursor = [], 0.0
    for token in tokens:
        span = duration * len(token) / total
        times.append((cursor, cursor + span))
        cursor += span
    return times


def _layout(tokens: List[str], max_chars: int) -> List[List[int]]:
    """Quebra gulosa em linhas de ate max_chars (uma palavra maior que isso fica sozinha)."""
    lines: List[List[int]] = [[]]
    size = 0
    for i, token in enumerate(tokens):
        add = len(token) + (1 if lines[-1] else 0)
        if lines[-1] and size + add > max_chars:
            lines.append([])
            size = 0
            add = len(token)
        lines[-1].append(i)
        size += add
    return lines


def _wrap(tokens: List[str], max_chars: int, max_lines: int, active=None, hl=None, base=None) -> str:
    """Junta os tokens em linhas; se `active` for dado, destaca essa palavra."""
    lines = _layout(tokens, max_chars)
    if len(lines) > max_lines:  # nao deveria ocorrer (os grupos ja cabem), mas nao perde texto
        lines = lines[: max_lines - 1] + [[i for line in lines[max_lines - 1:] for i in line]]
    out = []
    for line in lines:
        words = []
        for i in line:
            word = _escape_token(tokens[i])
            if active is not None and i == active:
                word = f"{{\\1c{hl}}}{word}{{\\1c{base}}}"
            words.append(word)
        out.append(" ".join(words))
    return "\\N".join(out)


def build_groups(segments: List[Dict], cfg: Dict) -> List[Dict]:
    """Agrupa palavras em blocos que cabem na tela, guardando o tempo de cada palavra."""
    max_chars, max_lines = int(cfg["max_chars_per_line"]), int(cfg["max_lines"])
    groups: List[Dict] = []
    for segment in segments:
        tokens = segment["text"].split()
        if not tokens:
            continue
        times = _token_times(segment, tokens)
        current = {"tokens": [], "times": []}
        for token, (start, end) in zip(tokens, times):
            if current["tokens"] and len(_layout(current["tokens"] + [token], max_chars)) > max_lines:
                groups.append(current)
                current = {"tokens": [], "times": []}
            current["tokens"].append(token)
            current["times"].append((segment["start"] + start, segment["start"] + end))
        groups.append(current)
        groups[-1]["times"][-1] = (groups[-1]["times"][-1][0], segment["start"] + segment["duration"])
    return groups


def _events(groups: List[Dict], style: Dict, cfg: Dict) -> List[Dict]:
    mode, events = style["mode"], []
    mc, ml = int(cfg["max_chars_per_line"]), int(cfg["max_lines"])
    for g in groups:
        tokens, times = g["tokens"], g["times"]
        if mode == "block":
            events.append({"start": times[0][0], "end": times[-1][1], "text": _wrap(tokens, mc, ml), "fx": "{\\fad(90,90)}"})
            continue
        for i, token in enumerate(tokens):
            start = times[i][0]
            end = times[i + 1][0] if i + 1 < len(tokens) else times[-1][1]
            if mode == "word":
                text = _escape_token(token)
                fx = "{\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)}"
            else:
                text = _wrap(tokens, mc, ml, active=i, hl=_tag_color(style["hl"]), base=_tag_color(style["primary"]))
                fx = ""
            events.append({"start": start, "end": end, "text": text, "fx": fx})
    for i, ev in enumerate(events):  # não invade o próximo nem pisca rápido demais
        ev["end"] = max(ev["end"], ev["start"] + (0.12 if mode != "block" else 0.4))
        if i + 1 < len(events):
            ev["end"] = min(ev["end"], events[i + 1]["start"])
    return events


def write_ass(segments: List[Dict], cfg: Dict, path: Path, width: int, height: int) -> Path:
    key = cfg.get("style", DEFAULT_STYLE)
    style = STYLES.get(key, STYLES[DEFAULT_STYLE])
    header = _ASS_HEADER.format(
        width=width, height=height, font=style["font"],
        font_size=int(int(cfg["font_size"]) * style["scale"]),
        primary=style["primary"], outline_color=style["outline_color"],
        outline=style["outline"], shadow=style["shadow"], border=style["border"],
        margin_v=int(cfg["margin_v"]),
    )
    glow = "{\\blur3}" if style.get("glow") else ""
    # Letras de fonte pesada ocupam ~0,62 do tamanho: limita os caracteres por linha
    # para o texto sempre caber na largura do video (menos as margens laterais).
    fit = int((width - 120) / (int(cfg["font_size"]) * style["scale"] * 0.62))
    cfg = {**cfg, "max_chars_per_line": max(8, min(int(cfg["max_chars_per_line"]), fit))}
    lines = [header]
    for ev in _events(build_groups(segments, cfg), style, cfg):
        text = ev["text"].strip()
        if cfg.get("uppercase"):
            text = text.upper()
        lines.append(
            f"Dialogue: 0,{_timestamp(ev['start'])},{_timestamp(ev['end'])},Default,,0,0,0,,{ev['fx']}{glow}{text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path
