"""Gera o arquivo .ass de legendas sincronizado com a narracao."""

from pathlib import Path
from typing import Dict, List

_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary},&H000000FF,{outline_color},&H64000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,60,60,{margin_v},1

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


def _token_times(segment: Dict, tokens: List[str]) -> List[tuple]:
    """Tempo (inicio, fim) relativo de cada token do texto.

    Usa os WordBoundary do Edge TTS quando a contagem bate; senao distribui
    proporcional ao numero de caracteres, que para TTS fica bem proximo.
    """
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


def _wrap(tokens: List[str], max_chars_per_line: int, max_lines: int) -> str:
    """Junta os tokens em ate max_lines linhas, separadas pela quebra do ASS."""
    lines: List[str] = []
    current = ""
    for token in map(_escape_token, tokens):
        candidate = f"{current} {token}".strip()
        if current and len(candidate) > max_chars_per_line and len(lines) < max_lines - 1:
            lines.append(current)
            current = token
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\\N".join(lines)


def build_events(segments: List[Dict], cfg: Dict) -> List[Dict]:
    """Agrupa palavras em blocos de legenda que cabem na tela."""
    max_chars_per_line = int(cfg["max_chars_per_line"])
    max_lines = int(cfg["max_lines"])
    budget = max_chars_per_line * max_lines
    events: List[Dict] = []

    for segment in segments:
        tokens = segment["text"].split()
        if not tokens:
            continue
        times = _token_times(segment, tokens)

        group: List[str] = []
        group_start = times[0][0]
        last_end = times[0][1]
        for token, (start, end) in zip(tokens, times):
            candidate_len = len(" ".join(group + [token]))
            if group and candidate_len > budget:
                events.append(
                    {
                        "start": segment["start"] + group_start,
                        "end": segment["start"] + last_end,
                        "text": _wrap(group, max_chars_per_line, max_lines),
                    }
                )
                group, group_start = [token], start
            else:
                if not group:
                    group_start = start
                group.append(token)
            last_end = end

        if group:
            events.append(
                {
                    "start": segment["start"] + group_start,
                    "end": segment["start"] + segment["duration"],
                    "text": _wrap(group, max_chars_per_line, max_lines),
                }
            )

    # nao deixa um bloco invadir o proximo nem piscar rapido demais
    for index, event in enumerate(events):
        limit = events[index + 1]["start"] if index + 1 < len(events) else None
        event["end"] = max(event["end"], event["start"] + 0.4)
        if limit is not None:
            event["end"] = min(event["end"], limit)
    return events


def write_ass(segments: List[Dict], cfg: Dict, path: Path, width: int, height: int) -> Path:
    events = build_events(segments, cfg)
    header = _ASS_HEADER.format(
        width=width,
        height=height,
        font=cfg["font"],
        font_size=int(cfg["font_size"]),
        primary=cfg["primary_color"],
        outline_color=cfg["outline_color"],
        outline=cfg["outline"],
        shadow=cfg["shadow"],
        margin_v=int(cfg["margin_v"]),
    )

    lines = [header]
    for event in events:
        text = event["text"].strip()
        if cfg.get("uppercase"):
            text = text.upper()
        lines.append(
            f"Dialogue: 0,{_timestamp(event['start'])},{_timestamp(event['end'])},"
            f"Default,,0,0,0,,{{\\fad(90,90)}}{text}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path
