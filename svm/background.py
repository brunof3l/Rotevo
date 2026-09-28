"""Cuida do gameplay de fundo: baixa uma vez do YouTube e sorteia um trecho."""

import random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import ffmpeg_utils
from .settings import load_backgrounds

# Margem para nao cair na intro/outro do video de gameplay.
_EDGE_MARGIN = 20.0


def local_files(backgrounds_dir: Path) -> List[str]:
    if not backgrounds_dir.is_dir():
        return []
    return sorted(p.name for p in backgrounds_dir.glob("*.mp4"))


def available_options(backgrounds_dir: Path) -> List[Dict]:
    """Fundos do backgrounds.json + qualquer mp4 que o usuario tenha colocado na pasta."""
    catalog = load_backgrounds()
    options: List[Dict] = []
    catalog_files = set()

    for key, (url, filename, credit) in catalog.items():
        catalog_files.add(filename)
        options.append(
            {
                "key": key,
                "label": f"{key} ({credit})",
                "filename": filename,
                "url": url,
                "downloaded": (backgrounds_dir / filename).is_file(),
            }
        )

    for filename in local_files(backgrounds_dir):
        if filename not in catalog_files:
            options.append(
                {
                    "key": f"file:{filename}",
                    "label": f"{filename} (arquivo local)",
                    "filename": filename,
                    "url": "",
                    "downloaded": True,
                }
            )
    return options


def resolve(choice: str, backgrounds_dir: Path) -> Tuple[Path, str]:
    """Devolve (caminho do arquivo, url para baixar se faltar)."""
    if choice.startswith("file:"):
        return backgrounds_dir / choice[5:], ""

    catalog = load_backgrounds()
    if choice not in catalog:
        if not catalog:
            raise RuntimeError("backgrounds.json vazio e nenhum fundo local encontrado.")
        choice = "minecraft" if "minecraft" in catalog else next(iter(catalog))
    url, filename, _credit = catalog[choice]
    return backgrounds_dir / filename, url


def ensure_downloaded(
    path: Path, url: str, on_message: Optional[Callable[[str], None]] = None
) -> Path:
    if path.is_file() and path.stat().st_size > 0:
        return path
    if not url:
        raise FileNotFoundError(
            f"O fundo {path.name} nao existe em {path.parent} e nao tem URL para baixar."
        )

    import yt_dlp  # import tardio: so precisa quando falta baixar

    path.parent.mkdir(parents=True, exist_ok=True)
    if on_message:
        on_message(
            "Baixando o gameplay de fundo do YouTube (arquivo grande, mas so na primeira vez)..."
        )

    options = {
        "format": "bestvideo[height<=1080]/best[height<=1080]",
        # A ORDEM aqui importa: resolucao primeiro, codec por ultimo. Preferir
        # codec antes da resolucao fazia o yt-dlp trazer H.264 em 360p em vez de
        # 1080p. Depois da resolucao: ~30fps (o video final e 30fps, 60 so dobra
        # o arquivo) e entao H.264 (AV1 decodifica lento e ja veio quebrado aqui).
        "format_sort": ["res:1080", "fps:30", "vcodec:h264"],
        "merge_output_format": "mp4",
        "outtmpl": str(path),
        "retries": 10,
        "fragment_retries": 10,
        # Baixa em pedacos de 10 MB: download longo e sequencial toma 403 do
        # YouTube no meio do caminho.
        "http_chunk_size": 10 * 1024 * 1024,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # O cliente "web" toma 403 e o "android" so entrega 360p neste video.
        # android_vr / tv_embedded expoem 1080p e baixam sem bloqueio.
        "extractor_args": {
            "youtube": {"player_client": ["android_vr", "tv_embedded", "android"]}
        },
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    if not path.is_file():
        raise RuntimeError(f"Download do fundo falhou: {url}")

    if not ffmpeg_utils.decodes_video(path):
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"O fundo baixado de {url} veio corrompido (nao decodifica) e foi apagado. "
            "Tente de novo ou escolha outro gameplay."
        )

    if on_message:
        on_message("Gameplay de fundo baixado.")
    return path


def pick_window(path: Path, needed_seconds: float) -> Tuple[float, int]:
    """Sorteia onde comecar. Devolve (segundo inicial, quantas vezes repetir o video).

    Se o gameplay for mais curto que a narracao, o video eh repetido em loop.
    """
    total = ffmpeg_utils.probe_duration(path)
    usable = total - 2 * _EDGE_MARGIN

    if usable <= needed_seconds:
        loops = int(needed_seconds // max(total, 1)) + 1
        return 0.0, loops
    return random.uniform(_EDGE_MARGIN, total - _EDGE_MARGIN - needed_seconds), 0
