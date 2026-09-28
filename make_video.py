#!/usr/bin/env python
"""Uso por linha de comando:  python make_video.py roteiro.txt --title "Minha historia" """

import argparse
import sys
from pathlib import Path

from svm import tts
from svm.pipeline import create_video
from svm.settings import ROOT, load_config, path_from_config
from svm.background import available_options


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Roteiro -> video narrado com gameplay de fundo")
    parser.add_argument("roteiro", nargs="?", help="arquivo .txt com o roteiro")
    parser.add_argument("--title", default="", help="titulo (vira o nome do arquivo final)")
    parser.add_argument("--voice", help="voz do Edge TTS, ex: pt-BR-AntonioNeural")
    parser.add_argument("--rate", help="velocidade da fala, ex: +10%%")
    parser.add_argument("--pitch", help="tom da voz, ex: -2Hz")
    parser.add_argument("--background", help="fundo (chave do backgrounds.json ou file:nome.mp4)")
    parser.add_argument("--no-captions", action="store_true", help="renderiza sem legendas")
    parser.add_argument("--keep-temp", action="store_true", help="mantem os arquivos temporarios")
    parser.add_argument("--list-voices", action="store_true", help="lista as vozes em portugues")
    parser.add_argument("--list-backgrounds", action="store_true", help="lista os fundos")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.list_voices:
        for voice in tts.list_voices("pt"):
            print(f"{voice['name']:<42} {voice['gender']:<10} {voice['locale']}")
        return 0

    if args.list_backgrounds:
        backgrounds_dir = path_from_config(load_config(), "backgrounds_dir")
        for option in available_options(backgrounds_dir):
            status = "baixado" if option["downloaded"] else "precisa baixar"
            print(f"{option['key']:<24} {status:<16} {option['label']}")
        return 0

    if not args.roteiro:
        print("Informe o arquivo do roteiro. Ex: python make_video.py roteiro.txt")
        return 1

    script_path = Path(args.roteiro)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    if not script_path.is_file():
        print(f"Nao encontrei o arquivo: {script_path}")
        return 1

    overrides: dict = {"tts": {}, "captions": {}, "background": {}}
    if args.voice:
        overrides["tts"]["voice"] = args.voice
    if args.rate:
        overrides["tts"]["rate"] = args.rate
    if args.pitch:
        overrides["tts"]["pitch"] = args.pitch
    if args.background:
        overrides["background"]["choice"] = args.background
    if args.no_captions:
        overrides["captions"]["enabled"] = False
    if args.keep_temp:
        overrides["keep_temp"] = True

    def progress(pct: float, message: str) -> None:
        print(f"[{pct:5.1f}%] {message}")

    script = script_path.read_text(encoding="utf-8")
    title = args.title or script_path.stem
    output = create_video(script, title=title, overrides=overrides, on_progress=progress)
    print(f"\nVideo salvo em: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
