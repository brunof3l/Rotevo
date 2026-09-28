#!/usr/bin/env python
"""Baixa (ou rebaixa) todos os gameplays de fundo em boa resolucao.

Uso:
    python baixar_fundos.py            # baixa so o que falta
    python baixar_fundos.py --refazer  # apaga e baixa tudo de novo (ex: veio em 360p)
"""

import argparse
import subprocess
import sys
import time

from svm import background, ffmpeg_utils
from svm.settings import load_backgrounds, load_config, path_from_config

MIN_HEIGHT = 720  # abaixo disso o video fica borrado no formato vertical
TENTATIVAS = 4
PAUSA_SEGUNDOS = 90  # o YouTube responde 403 depois de muitos GB seguidos


def video_info(path) -> str:
    out = subprocess.run(
        [
            ffmpeg_utils.binary("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def height_of(path) -> int:
    info = video_info(path).split(",")
    return int(info[2]) if len(info) >= 3 and info[2].isdigit() else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refazer", action="store_true", help="rebaixa mesmo se ja existir")
    args = parser.parse_args()

    backgrounds_dir = path_from_config(load_config(), "backgrounds_dir")
    backgrounds_dir.mkdir(parents=True, exist_ok=True)
    falhas = []

    for key in load_backgrounds():
        path, url = background.resolve(key, backgrounds_dir)

        if path.is_file():
            altura = height_of(path)
            if args.refazer or altura < MIN_HEIGHT:
                motivo = "--refazer" if args.refazer else f"so {altura}p"
                print(f"{key}: rebaixando ({motivo})...")
                path.unlink()
            else:
                print(f"{key}: ok ({video_info(path)}, {round(path.stat().st_size/1_000_000)} MB)")
                continue
        else:
            print(f"{key}: baixando...")

        # O 403 do YouTube e temporario: uma pausa entre as tentativas resolve.
        # O yt-dlp retoma do .part, entao nada do que ja baixou se perde.
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                background.ensure_downloaded(path, url)
                print(f"{key}: OK -> {video_info(path)}, {round(path.stat().st_size/1_000_000)} MB")
                break
            except Exception as err:
                erro = str(err)[:110]
                if tentativa == TENTATIVAS:
                    falhas.append(key)
                    print(f"{key}: FALHOU depois de {TENTATIVAS} tentativas -> {erro}")
                else:
                    print(f"{key}: tentativa {tentativa} falhou ({erro})")
                    print(f"{key}: aguardando {PAUSA_SEGUNDOS}s antes de tentar de novo...")
                    time.sleep(PAUSA_SEGUNDOS)

    print("---")
    print("falhas:", ", ".join(falhas) if falhas else "nenhuma")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
