#!/usr/bin/env python
"""Interface web local: cola o roteiro, escolhe a voz, gera o video."""

import os
import socket
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path
from typing import Dict

from flask import Flask, jsonify, render_template, request, send_from_directory

from svm import tts
from svm.background import available_options
from svm.pipeline import create_video
from svm.settings import load_config, path_from_config, save_config
from svm.textsplit import estimate_seconds, split_script

app = Flask(__name__)

JOBS: Dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
_VOICE_CACHE: Dict[str, list] = {}


def _update(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(fields)


def _log(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        log = JOBS[job_id]["log"]
        if not log or log[-1] != message:
            log.append(message)
            del log[:-40]


def _run_job(job_id: str, script: str, title: str, overrides: dict) -> None:
    def progress(pct: float, message: str) -> None:
        _update(job_id, progress=round(pct, 1), step=message)
        _log(job_id, message)

    try:
        output = create_video(script, title=title, overrides=overrides, on_progress=progress)
        _update(job_id, status="done", progress=100, file=output.name)
    except Exception as err:
        traceback.print_exc()
        _update(job_id, status="error", error=str(err))
        _log(job_id, f"ERRO: {err}")


@app.get("/")
def index():
    config = load_config()
    backgrounds = available_options(path_from_config(config, "backgrounds_dir"))
    return render_template("index.html", config=config, backgrounds=backgrounds)


@app.get("/api/voices")
def api_voices():
    prefix = request.args.get("lang", "pt")
    if prefix not in _VOICE_CACHE:
        try:
            _VOICE_CACHE[prefix] = tts.list_voices(prefix)
        except Exception as err:
            return jsonify({"error": str(err), "voices": []}), 200
    return jsonify({"voices": _VOICE_CACHE[prefix]})


@app.post("/api/preview")
def api_preview():
    script = (request.json or {}).get("script", "")
    chunks = split_script(script)
    return jsonify(
        {
            "chars": len(script),
            "blocks": len(chunks),
            "estimated_seconds": round(estimate_seconds(script)),
        }
    )


@app.post("/api/generate")
def api_generate():
    data = request.json or {}
    script = (data.get("script") or "").strip()
    if not script:
        return jsonify({"error": "Cole o roteiro antes de gerar."}), 400

    overrides = {
        "tts": {
            "voice": data.get("voice") or load_config()["tts"]["voice"],
            "rate": f"{int(data.get('rate', 0)):+d}%",
            "pitch": f"{int(data.get('pitch', 0)):+d}Hz",
        },
        "captions": {
            "enabled": bool(data.get("captions", True)),
            "uppercase": bool(data.get("uppercase", False)),
        },
        "background": {"choice": data.get("background") or "minecraft"},
    }
    if data.get("font_size"):
        overrides["captions"]["font_size"] = int(data["font_size"])

    if data.get("save_defaults"):
        config = load_config()
        config["tts"].update(overrides["tts"])
        config["captions"].update(overrides["captions"])
        config["background"]["choice"] = overrides["background"]["choice"]
        save_config(config)

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "progress": 0,
            "step": "Na fila...",
            "log": [],
            "file": None,
            "error": None,
            "title": data.get("title") or "video",
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, script, data.get("title") or "", overrides),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/status/<job_id>")
def api_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job desconhecido"}), 404
        return jsonify(dict(job))


@app.get("/videos/<path:filename>")
def videos(filename: str):
    output_dir = path_from_config(load_config(), "output_dir")
    return send_from_directory(output_dir, filename)


@app.post("/api/shutdown")
def api_shutdown():
    """Desliga o servidor (o atalho roda ele sem janela, entao o site e o unico lugar de parar)."""
    with JOBS_LOCK:
        busy = any(job["status"] == "running" for job in JOBS.values())
    if busy:
        return jsonify({"error": "Tem um video sendo gerado. Espere terminar para desligar."}), 409
    threading.Timer(0.6, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


@app.get("/api/outputs")
def api_outputs():
    output_dir: Path = path_from_config(load_config(), "output_dir")
    if not output_dir.is_dir():
        return jsonify({"videos": []})
    files = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonify(
        {
            "videos": [
                {"name": f.name, "size_mb": round(f.stat().st_size / 1_000_000, 1)}
                for f in files[:20]
            ]
        }
    )


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    url = "http://127.0.0.1:5000"
    if _port_in_use(5000):
        # Ja tem um servidor de pe (o atalho foi clicado de novo): so abre o site.
        webbrowser.open(url)
    else:
        print(f"\n  Script Video Maker rodando em {url}\n")
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
