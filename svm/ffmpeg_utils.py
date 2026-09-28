"""Localiza e executa ffmpeg/ffprobe, com progresso."""

import json
import shutil
import subprocess
import threading
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Sequence

from .settings import ROOT

# Onde procurar os binarios, em ordem: PATH, bin/ do projeto, o ffmpeg que veio
# junto com o RedditVideoMakerBot (projeto irmao).
_EXTRA_DIRS = [ROOT / "bin", ROOT.parent / "RedditVideoMakerBot"]

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


class FFmpegNotFound(RuntimeError):
    pass


@lru_cache(maxsize=4)
def binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for directory in _EXTRA_DIRS:
        for candidate in (directory / f"{name}.exe", directory / name):
            if candidate.is_file():
                return str(candidate)
    raise FFmpegNotFound(
        f"Nao encontrei o {name}. Instale o FFmpeg e coloque no PATH, "
        f"ou copie {name}.exe para a pasta bin/ deste projeto."
    )


def probe_duration(path: str | Path) -> float:
    out = subprocess.run(
        [
            binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe falhou em {path}: {out.stderr.strip()}")
    return float(json.loads(out.stdout)["format"]["duration"])


def stream_types(path: str | Path) -> list:
    """Tipos de stream do arquivo, ex: ['video', 'audio']."""
    out = subprocess.run(
        [
            binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )
    if out.returncode != 0:
        return []
    return [s.get("codec_type") for s in json.loads(out.stdout).get("streams", [])]


def decodes_video(path: str | Path, at_second: float = 60.0) -> bool:
    """Confere se o video realmente decodifica (arquivo baixado pode vir corrompido)."""
    out = subprocess.run(
        [
            binary("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(at_second),
            "-i",
            str(path),
            "-frames:v",
            "5",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )
    return out.returncode == 0 and "Error while decoding" not in out.stderr


def has_encoder(name: str) -> bool:
    out = subprocess.run(
        [binary("ffmpeg"), "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )
    return f" {name} " in out.stdout


def run(
    args: Sequence[str],
    cwd: Optional[Path] = None,
    total_seconds: Optional[float] = None,
    on_progress: Optional[Callable[[float], None]] = None,
) -> None:
    """Roda ffmpeg. Se total_seconds e on_progress vierem, reporta 0..1 do encode."""
    cmd = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if on_progress and total_seconds:
        cmd += ["-progress", "pipe:1", "-nostats"]
    cmd += list(args)

    process = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )

    # O stderr PRECISA ser drenado numa thread propria: alguns videos (AV1, por
    # exemplo) despejam dezenas de KB de aviso, enchem o buffer do pipe e o
    # ffmpeg trava esperando alguem ler enquanto nos so liamos o stdout.
    stderr_tail: deque = deque(maxlen=40)

    def drain_stderr() -> None:
        for line in process.stderr:  # type: ignore[union-attr]
            line = line.strip()
            if line:
                stderr_tail.append(line)

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()

    for line in process.stdout:  # type: ignore[union-attr]
        if on_progress and total_seconds and line.startswith("out_time_ms="):
            value = line.split("=", 1)[1].strip()
            if value.isdigit():
                on_progress(min(1.0, int(value) / 1_000_000 / total_seconds))

    process.wait()
    reader.join(timeout=5)
    if process.returncode != 0:
        raise RuntimeError("ffmpeg falhou:\n" + "\n".join(list(stderr_tail)[-12:]))


def make_silence(path: Path, seconds: float, sample_rate: int = 44100) -> None:
    run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={sample_rate}:cl=stereo",
            "-t",
            f"{seconds:.3f}",
            str(path),
        ]
    )


def to_wav(src: Path, dst: Path, sample_rate: int = 44100) -> None:
    run(["-y", "-i", str(src), "-ar", str(sample_rate), "-ac", "2", str(dst)])


def concat_audio(list_file: Path, dst: Path, sample_rate: int = 44100) -> None:
    """Concatena via demuxer. list_file usa nomes relativos ao proprio diretorio."""
    run(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file.name,
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            str(dst),
        ],
        cwd=list_file.parent,
    )
