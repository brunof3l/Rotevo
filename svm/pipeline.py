"""Orquestra tudo: roteiro -> narracao IA -> legendas -> gameplay de fundo -> mp4."""

import re
import shutil
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import background, captions, ffmpeg_utils, tts
from .settings import ROOT, load_config, path_from_config
from .textsplit import split_script

ProgressFn = Callable[[float, str], None]


def _noop(_pct: float, _msg: str) -> None:
    pass


def slugify(text: str, fallback: str = "video") -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60].strip("-") or fallback


def _build_narration(
    segments: List[Dict], work_dir: Path, gap_seconds: float
) -> tuple[Path, List[Dict]]:
    """Converte os mp3 para wav, monta a linha do tempo e concatena tudo."""
    silence = work_dir / "silence.wav"
    if gap_seconds > 0:
        ffmpeg_utils.make_silence(silence, gap_seconds)

    entries: List[str] = []
    cursor = 0.0
    for position, segment in enumerate(segments):
        wav = work_dir / f"{segment['index']:04d}.wav"
        ffmpeg_utils.to_wav(segment["path"], wav)
        duration = ffmpeg_utils.probe_duration(wav)

        segment["start"] = cursor
        segment["duration"] = duration
        entries.append(f"file '{wav.name}'")
        cursor += duration

        if gap_seconds > 0 and position < len(segments) - 1:
            entries.append(f"file '{silence.name}'")
            cursor += gap_seconds

    list_file = work_dir / "concat.txt"
    list_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

    narration = work_dir / "narration.wav"
    ffmpeg_utils.concat_audio(list_file, narration)
    return narration, segments


def _video_args(cfg: Dict) -> List[str]:
    encoder = cfg["video"]["encoder"]
    crf = int(cfg["video"]["crf"])
    if encoder != "libx264" and not ffmpeg_utils.has_encoder(encoder):
        encoder = "libx264"
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf)]
    return ["-c:v", encoder, "-preset", cfg["video"]["preset"], "-crf", str(crf)]


def create_video(
    script: str,
    title: str = "",
    overrides: Optional[Dict] = None,
    on_progress: ProgressFn = _noop,
) -> Path:
    """Gera o video e devolve o caminho do mp4 final."""
    cfg = load_config(overrides)
    started = time.time()

    output_dir = path_from_config(cfg, "output_dir")
    temp_root = path_from_config(cfg, "temp_dir")
    backgrounds_dir = path_from_config(cfg, "backgrounds_dir")
    output_dir.mkdir(parents=True, exist_ok=True)
    backgrounds_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{slugify(title or script[:60])}-{stamp}"
    work_dir = temp_root / name
    (work_dir / "audio").mkdir(parents=True, exist_ok=True)

    try:
        on_progress(2, "Preparando o roteiro...")
        chunks = split_script(
            script,
            min_chars=int(cfg["text"]["min_chars"]),
            max_chars=int(cfg["text"]["max_chars"]),
        )
        if not chunks:
            raise ValueError("O roteiro esta vazio depois da limpeza. Cole algum texto.")
        on_progress(5, f"Roteiro dividido em {len(chunks)} blocos de narracao.")

        # 1) narracao
        def tts_progress(done: int, total: int) -> None:
            on_progress(5 + 40 * done / total, f"Narrando com IA... ({done}/{total} blocos)")

        segments = tts.synthesize(
            chunks,
            work_dir / "audio",
            voice=cfg["tts"]["voice"],
            rate=cfg["tts"]["rate"],
            pitch=cfg["tts"]["pitch"],
            volume=cfg["tts"]["volume"],
            concurrency=int(cfg["tts"]["concurrency"]),
            on_done=tts_progress,
        )

        on_progress(46, "Montando a faixa de narracao...")
        narration, segments = _build_narration(
            segments, work_dir / "audio", float(cfg["tts"]["gap_seconds"])
        )
        narration_seconds = ffmpeg_utils.probe_duration(narration)
        total_seconds = narration_seconds + float(cfg["video"]["tail_seconds"])
        on_progress(55, f"Narracao pronta: {narration_seconds / 60:.1f} min.")

        # 2) gameplay de fundo
        bg_path, bg_url = background.resolve(cfg["background"]["choice"], backgrounds_dir)
        background.ensure_downloaded(bg_path, bg_url, lambda msg: on_progress(57, msg))
        start_at, loops = background.pick_window(bg_path, total_seconds)
        on_progress(62, "Trecho do gameplay escolhido.")

        # 3) legendas
        use_captions = bool(cfg["captions"]["enabled"])
        if use_captions:
            captions.write_ass(
                segments,
                cfg["captions"],
                work_dir / "captions.ass",
                int(cfg["video"]["width"]),
                int(cfg["video"]["height"]),
            )
            on_progress(65, "Legendas geradas.")

        # 4) render final
        width, height, fps = (
            int(cfg["video"]["width"]),
            int(cfg["video"]["height"]),
            int(cfg["video"]["fps"]),
        )
        args: List[str] = ["-y"]
        if loops:
            args += ["-stream_loop", str(loops)]
        elif start_at > 0:
            args += ["-ss", f"{start_at:.3f}"]
        args += ["-i", str(bg_path), "-i", str(narration)]

        music_file = (cfg["background"].get("music_file") or "").strip()
        music_path = Path(music_file)
        if music_file and not music_path.is_absolute():
            music_path = ROOT / music_file
        use_music = bool(music_file) and music_path.is_file()
        if use_music:
            args += ["-stream_loop", "-1", "-i", str(music_path)]

        video_chain = (
            f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )
        video_chain += ",subtitles=captions.ass[v]" if use_captions else "[v]"

        tail = float(cfg["video"]["tail_seconds"])
        if use_music:
            volume = float(cfg["background"]["music_volume"])
            audio_chain = (
                "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[narr];"
                f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={volume}[bgm];"
                "[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                f"apad=pad_dur={tail}[a]"
            )
        else:
            audio_chain = (
                "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                f"apad=pad_dur={tail}[a]"
            )

        output_path = output_dir / f"{name}.mp4"
        args += [
            "-filter_complex",
            f"{video_chain};{audio_chain}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{total_seconds:.3f}",
            *_video_args(cfg),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        on_progress(66, "Renderizando o video (parte mais demorada)...")
        ffmpeg_utils.run(
            args,
            cwd=work_dir,
            total_seconds=total_seconds,
            on_progress=lambda frac: on_progress(
                66 + 33 * frac, f"Renderizando... {frac * 100:.0f}%"
            ),
        )

        # O ffmpeg pode sair com sucesso e mesmo assim nao gravar imagem nenhuma
        # (fundo corrompido, por exemplo). Melhor falhar aqui do que entregar
        # um "video" so com audio.
        if "video" not in ffmpeg_utils.stream_types(output_path):
            raise RuntimeError(
                f"O render saiu sem imagem. O gameplay de fundo ({bg_path.name}) provavelmente "
                f"esta corrompido: apague o arquivo em {bg_path.parent} para baixar de novo."
            )

        (output_dir / f"{name}.txt").write_text(script.strip(), encoding="utf-8")
        on_progress(100, f"Pronto em {time.time() - started:.0f}s: {output_path.name}")
        return output_path
    finally:
        if not cfg.get("keep_temp") and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
