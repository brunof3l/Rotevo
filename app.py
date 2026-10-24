#!/usr/bin/env python
"""Rotevo — interface web local: cola o roteiro, escolhe voz e legenda, gera o vídeo."""

import os
import re
import secrets
import socket
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from flask import Flask, g, jsonify, render_template, request, send_from_directory

from svm import tts
from svm.background import available_options
from svm.captions import STYLES
from svm.pipeline import create_video
from svm.settings import ROOT, load_config, path_from_config, save_config
from svm.textsplit import estimate_seconds, split_script

PORT = 5000
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
MAX_SCRIPT_CHARS = 10_000
MAX_TITLE_CHARS = 80
VOICE_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+$")
VIDEO_RE = re.compile(r"^[\w.-]{1,120}\.mp4$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # corpo máximo de 64 KB

JOBS: Dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
_VOICE_CACHE: Dict[str, list] = {}


# ---------------------------------------------------------------- segurança
@app.before_request
def _guard():
    g.nonce = secrets.token_urlsafe(16)
    # Proteção contra DNS rebinding: só aceita Host local.
    if request.host not in ALLOWED_HOSTS:
        return jsonify({"error": "Host não permitido."}), 403
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc not in ALLOWED_HOSTS:  # anti-CSRF
            return jsonify({"error": "Origem não permitida."}), 403
        if not request.is_json:
            return jsonify({"error": "Requisição inválida."}), 415


@app.after_request
def _headers(resp):
    nonce = getattr(g, "nonce", "")
    resp.headers["Content-Security-Policy"] = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
        "img-src 'self' data:; media-src 'self'; connect-src 'self'; font-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.context_processor
def _nonce():
    return {"nonce": getattr(g, "nonce", "")}


def _clamp(value, low, high, default):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _safe_error(err: Exception) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(err)).replace(str(ROOT), "<projeto>")
    return (text[:220] or "Erro inesperado ao gerar o vídeo.")


# ------------------------------------------------------------------- jobs
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
        _update(job_id, status="error", error=_safe_error(err))


# ----------------------------------------------------------------- rotas
@app.get("/")
def index():
    config = load_config()
    backgrounds = available_options(path_from_config(config, "backgrounds_dir"))
    styles = [{"key": k, "label": v["label"]} for k, v in STYLES.items()]
    return render_template("index.html", config=config, backgrounds=backgrounds, styles=styles)


@app.get("/api/voices")
def api_voices():
    prefix = request.args.get("lang", "pt")
    if not re.fullmatch(r"[a-z]{2,3}", prefix):
        prefix = "pt"
    if prefix not in _VOICE_CACHE:
        try:
            _VOICE_CACHE[prefix] = tts.list_voices(prefix)
        except Exception:
            return jsonify({"error": "Não foi possível carregar as vozes (sem internet?).", "voices": []})
    return jsonify({"voices": _VOICE_CACHE[prefix]})


@app.post("/api/preview")
def api_preview():
    script = str((request.json or {}).get("script", ""))[:MAX_SCRIPT_CHARS]
    return jsonify(
        {
            "chars": len(script),
            "blocks": len(split_script(script)),
            "estimated_seconds": round(estimate_seconds(script)),
        }
    )


@app.post("/api/generate")
def api_generate():
    data = request.json or {}
    script = str(data.get("script") or "").strip()
    title = str(data.get("title") or "").strip()[:MAX_TITLE_CHARS]
    if not script:
        return jsonify({"error": "Cole o roteiro antes de gerar."}), 400
    if len(script) > MAX_SCRIPT_CHARS:
        return jsonify({"error": f"O roteiro passa do limite de {MAX_SCRIPT_CHARS} caracteres."}), 400

    config = load_config()
    voice = str(data.get("voice") or config["tts"]["voice"])
    if not VOICE_RE.match(voice):
        return jsonify({"error": "Voz inválida."}), 400

    valid_backgrounds = {o["key"] for o in available_options(path_from_config(config, "backgrounds_dir"))}
    background = str(data.get("background") or config["background"]["choice"])
    if background not in valid_backgrounds:
        return jsonify({"error": "Fundo inválido."}), 400

    style = str(data.get("caption_style") or "classico")
    if style not in STYLES:
        return jsonify({"error": "Estilo de legenda inválido."}), 400

    overrides = {
        "tts": {
            "voice": voice,
            "rate": f"{_clamp(data.get('rate'), -30, 60, 0):+d}%",
            "pitch": f"{_clamp(data.get('pitch'), -12, 12, 0):+d}Hz",
        },
        "captions": {
            "enabled": bool(data.get("captions", True)),
            "uppercase": bool(data.get("uppercase", False)),
            "style": style,
            "font_size": _clamp(data.get("font_size"), 40, 120, 76),
        },
        "background": {"choice": background},
    }

    if data.get("save_defaults"):
        config["tts"].update(overrides["tts"])
        config["captions"].update(overrides["captions"])
        config["background"]["choice"] = background
        save_config(config)

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        if any(j["status"] == "running" for j in JOBS.values()):  # um vídeo por vez
            return jsonify({"error": "Já existe um vídeo sendo gerado. Aguarde terminar."}), 409
        JOBS[job_id] = {"status": "running", "progress": 0, "step": "Na fila...", "log": [], "file": None, "error": None}
        for old in list(JOBS)[:-30]:  # não deixa a memória crescer
            JOBS.pop(old, None)

    threading.Thread(target=_run_job, args=(job_id, script, title, overrides), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/api/status/<job_id>")
def api_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Tarefa desconhecida."}), 404
        return jsonify(dict(job))


@app.get("/videos/<path:filename>")
def videos(filename: str):
    if not VIDEO_RE.match(filename):
        return jsonify({"error": "Arquivo inválido."}), 404
    output_dir = path_from_config(load_config(), "output_dir")
    return send_from_directory(output_dir, filename, mimetype="video/mp4", as_attachment=request.args.get("dl") == "1")


@app.post("/api/shutdown")
def api_shutdown():
    with JOBS_LOCK:
        busy = any(job["status"] == "running" for job in JOBS.values())
    if busy:
        return jsonify({"error": "Tem um vídeo sendo gerado. Espere terminar para desligar."}), 409
    threading.Timer(0.6, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


@app.get("/api/outputs")
def api_outputs():
    output_dir: Path = path_from_config(load_config(), "output_dir")
    if not output_dir.is_dir():
        return jsonify({"videos": []})
    files = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonify({"videos": [{"name": f.name, "size_mb": round(f.stat().st_size / 1_000_000, 1)} for f in files[:20]]})


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}"
    if _port_in_use(PORT):
        webbrowser.open(url)
    else:
        print(f"\n  Rotevo rodando em {url}\n")
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
