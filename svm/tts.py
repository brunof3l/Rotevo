"""Narracao com Edge TTS (vozes neurais da Microsoft, gratis e sem API key)."""

import asyncio
from pathlib import Path
from typing import Callable, Dict, List, Optional

import edge_tts

# edge-tts devolve tempos em unidades de 100 nanossegundos.
_TICKS_PER_SECOND = 10_000_000
_MAX_ATTEMPTS = 3


class TTSError(RuntimeError):
    pass


async def _synth_one(text: str, out_path: Path, voice: str, rate: str, pitch: str, volume: str):
    """Sintetiza um bloco e devolve os tempos por palavra (WordBoundary)."""
    last_error: Optional[Exception] = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        words: List[Dict] = []
        audio = bytearray()
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    words.append(
                        {
                            "text": chunk["text"],
                            "start": chunk["offset"] / _TICKS_PER_SECOND,
                            "end": (chunk["offset"] + chunk["duration"]) / _TICKS_PER_SECOND,
                        }
                    )
            if not audio:
                raise TTSError("a voz devolveu audio vazio")
            out_path.write_bytes(bytes(audio))
            return words
        except Exception as err:  # rede instavel / bloco recusado -> tenta de novo
            last_error = err
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(1.5 * attempt)
    raise TTSError(f"Edge TTS falhou depois de {_MAX_ATTEMPTS} tentativas: {last_error}")


async def _synth_all(
    chunks: List[str],
    out_dir: Path,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    concurrency: int,
    on_done: Optional[Callable[[int, int], None]],
) -> List[Dict]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: List[Optional[Dict]] = [None] * len(chunks)
    completed = 0
    lock = asyncio.Lock()

    async def worker(index: int, text: str):
        nonlocal completed
        path = out_dir / f"{index:04d}.mp3"
        async with semaphore:
            words = await _synth_one(text, path, voice, rate, pitch, volume)
        results[index] = {"index": index, "text": text, "path": path, "words": words}
        async with lock:
            completed += 1
            if on_done:
                on_done(completed, len(chunks))

    await asyncio.gather(*(worker(i, t) for i, t in enumerate(chunks)))
    return [r for r in results if r]


def synthesize(
    chunks: List[str],
    out_dir: Path,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%",
    concurrency: int = 3,
    on_done: Optional[Callable[[int, int], None]] = None,
) -> List[Dict]:
    """Gera um mp3 por bloco. Devolve [{index, text, path, words}] na ordem do roteiro."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(
        _synth_all(chunks, out_dir, voice, rate, pitch, volume, concurrency, on_done)
    )


def list_voices(language_prefix: Optional[str] = None) -> List[Dict]:
    """Vozes disponiveis, opcionalmente filtradas por prefixo ('pt', 'pt-BR', 'en')."""
    voices = asyncio.run(edge_tts.list_voices())
    items = [
        {
            "name": v["ShortName"],
            "gender": "Feminina" if v.get("Gender") == "Female" else "Masculina",
            "locale": v.get("Locale", ""),
        }
        for v in voices
    ]
    if language_prefix:
        items = [v for v in items if v["locale"].lower().startswith(language_prefix.lower())]
    return sorted(items, key=lambda v: (v["locale"], v["name"]))
