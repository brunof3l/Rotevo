"""Quebra o roteiro colado em blocos de narracao (um bloco = um arquivo de TTS)."""

import re
from typing import List

# Abreviacoes que terminam em ponto e NAO encerram frase.
_ABBREVIATIONS = [
    "sr",
    "sra",
    "srta",
    "dr",
    "dra",
    "prof",
    "profa",
    "eng",
    "av",
    "ex",
    "etc",
    "mr",
    "mrs",
    "ms",
    "vs",
    "no",
    "num",
]
_ABBREV_RE = re.compile(r"\b(" + "|".join(_ABBREVIATIONS) + r")\.\s", flags=re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")
_SOFT_BREAK_RE = re.compile(r"(?<=[,;:])\s+")

# Marcador interno para o ponto de abreviacoes, some antes de sair da funcao.
_DOT_SENTINEL = chr(1)


def clean_for_tts(text: str) -> str:
    """Tira marcacao de roteiro que a voz nao deve ler."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _URL_RE.sub(" ", text)
    # marcadores de markdown / roteiro: **negrito**, _italico_, # titulo, - lista
    text = re.sub(r"[*_`~]+", "", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-•>]\s+", "", text, flags=re.MULTILINE)
    # anotacoes de producao: [pausa], (musica sobe)
    text = re.sub(r"\[[^\]\n]{0,80}\]", " ", text)
    text = re.sub(r"\([^)\n]{0,80}\)", " ", text)
    # espacos e linhas em excesso
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _protect_abbreviations(text: str) -> str:
    """Troca o ponto da abreviacao por um sentinela para nao virar fim de frase."""
    return _ABBREV_RE.sub(lambda m: m.group(0).replace(".", _DOT_SENTINEL), text)


def _restore_abbreviations(text: str) -> str:
    return text.replace(_DOT_SENTINEL, ".")


def _hard_split(chunk: str, max_chars: int) -> List[str]:
    """Quebra um bloco grande demais: primeiro em virgulas, depois em palavras."""
    if len(chunk) <= max_chars:
        return [chunk]

    parts: List[str] = []
    buffer = ""
    for piece in _SOFT_BREAK_RE.split(chunk):
        candidate = f"{buffer} {piece}".strip()
        if buffer and len(candidate) > max_chars:
            parts.append(buffer)
            buffer = piece
        else:
            buffer = candidate
    if buffer:
        parts.append(buffer)

    result: List[str] = []
    for part in parts:
        while len(part) > max_chars:
            cut = part.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            result.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            result.append(part)
    return result


def split_script(text: str, min_chars: int = 60, max_chars: int = 240) -> List[str]:
    """Roteiro -> lista de blocos.

    Blocos curtos demais grudam no anterior (evita narracao picotada) e blocos
    longos demais sao quebrados (evita legenda gigante e falha de sintese).
    """
    text = clean_for_tts(text)
    if not text:
        return []

    raw: List[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        for line in paragraph.split("\n"):
            line = line.strip()
            if not line:
                continue
            for sentence in _SENTENCE_END_RE.split(_protect_abbreviations(line)):
                sentence = _restore_abbreviations(sentence).strip()
                if sentence:
                    raw.append(sentence)

    merged: List[str] = []
    for sentence in raw:
        too_short = merged and len(merged[-1]) < min_chars
        if too_short and len(merged[-1]) + len(sentence) + 1 <= max_chars:
            merged[-1] = f"{merged[-1]} {sentence}"
        else:
            merged.append(sentence)

    chunks: List[str] = []
    for sentence in merged:
        chunks.extend(_hard_split(sentence, max_chars))

    # garante pontuacao final para a voz nao emendar os blocos
    return [c if c[-1] in ".!?…,;:" else f"{c}." for c in chunks if c.strip()]


def estimate_seconds(text: str, chars_per_second: float = 14.5) -> float:
    """Estimativa grosseira de duracao, so para mostrar na interface."""
    return len(clean_for_tts(text)) / chars_per_second
