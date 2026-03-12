from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from flask import Flask, abort, jsonify, render_template, request, send_file, send_from_directory
from PIL import Image

from manga_translate import (
    IMAGE_SUFFIXES,
    detect_model,
    natural_sort_key,
    normalize_endpoint,
    run_translation_job,
)


ROOT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
JOBS_DIR = ROOT_DIR / "web_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7861

app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))

STATE_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}
SERVER_OPTIONS: dict[str, Any] = {
    "model_preset": "7b",
    "startup_timeout": 300,
    "auto_start_model": False,
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def endpoint_for_preset(model_preset: str) -> str:
    port = 8000 if model_preset == "30b" else 8001
    return f"http://127.0.0.1:{port}/v1"


def health_url_for_preset(model_preset: str) -> str:
    port = 8000 if model_preset == "30b" else 8001
    return f"http://127.0.0.1:{port}/health"


def set_server_options(args: argparse.Namespace) -> None:
    SERVER_OPTIONS["model_preset"] = args.model_preset
    SERVER_OPTIONS["startup_timeout"] = args.startup_timeout
    SERVER_OPTIONS["auto_start_model"] = args.auto_start_model


def probe_endpoint(endpoint: str, timeout: int = 5) -> dict[str, Any]:
    normalized = normalize_endpoint(endpoint)
    try:
        model_id = detect_model(normalized, timeout)
    except (RuntimeError, HTTPError, URLError, TimeoutError) as exc:
        return {
            "endpoint": normalized,
            "healthy": False,
            "model": None,
            "error": str(exc),
        }

    return {
        "endpoint": normalized,
        "healthy": True,
        "model": model_id,
        "error": "",
    }


def find_online_endpoint(timeout: int = 5) -> dict[str, Any] | None:
    for model_preset in ("7b", "30b"):
        result = probe_endpoint(endpoint_for_preset(model_preset), timeout=timeout)
        if result["healthy"]:
            result["model_preset"] = model_preset
            return result
    return None


def wait_for_healthy_endpoint(endpoint: str, timeout: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_result = probe_endpoint(endpoint, timeout=5)
    while time.time() < deadline:
        if last_result["healthy"]:
            return last_result
        time.sleep(5)
        last_result = probe_endpoint(endpoint, timeout=5)
    return last_result


def start_model(model_preset: str, timeout: int) -> dict[str, Any]:
    command = [
        "wsl",
        "-d",
        "Ubuntu",
        "-e",
        "bash",
        "-lc",
        f"~/workspace/start_vllm.sh {model_preset}",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    endpoint = endpoint_for_preset(model_preset)
    health = wait_for_healthy_endpoint(endpoint, timeout=timeout)
    health["startup_output"] = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    health["model_preset"] = model_preset
    return health


def ensure_model_online(model_preset: str, start_if_needed: bool, timeout: int) -> dict[str, Any]:
    port = 8000 if model_preset == "30b" else 8001
    online = find_online_endpoint(timeout=5)
    if online is not None:
        return online
    if not start_if_needed:
        raise RuntimeError(
            f"无法连接到本地 Qwen-VL 服务 (尝试 {model_preset} 模型，端口 {port})。\n\n"
            "请检查以下事项：\n"
            "1. WSL (Ubuntu) 是否已启动\n"
            f"2. vLLM 服务是否正在运行 (端口 {port})\n"
            "3. 如果使用自动启动，请确认 ~/workspace/start_vllm.sh 脚本存在\n\n"
            "或在前端勾选「自动启动模型」选项。"
        )

    result = start_model(model_preset, timeout=timeout)
    if not result["healthy"]:
        raise RuntimeError(
            f"启动本地 Qwen 服务失败 (尝试 {model_preset} 模型，端口 {port})。\n\n"
            f"错误信息: {result.get('error') or '未知错误'}\n\n"
            "请检查：\n"
            "1. WSL Ubuntu 是否正常运行\n"
            "2. ~/workspace/start_vllm.sh 脚本是否存在并可执行\n"
            f"3. vLLM 启动日志: ~/workspace/logs/vllm-{model_preset}.log"
        )
    return result


def update_job(job_id: str, **updates: Any) -> dict[str, Any]:
    with STATE_LOCK:
        job = JOBS[job_id]
        job.update(updates)
        job["updated_at"] = now_iso()
        return job.copy()


def job_response(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "status": job["status"],
        "message": job["message"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "progress": job["progress"],
        "downloads": job.get("downloads", {}),
        "result": job.get("result"),
        "error": job.get("error", ""),
        "settings": job.get("settings", {}),
    }


def safe_filename(name: str, fallback_index: int) -> str:
    cleaned = Path(name or f"page_{fallback_index:03d}.png").name.strip()
    cleaned = cleaned.replace("\x00", "")
    if not cleaned:
        cleaned = f"page_{fallback_index:03d}.png"
    return cleaned


def dedupe_name(target_dir: Path, filename: str) -> str:
    candidate = filename
    counter = 2
    while (target_dir / candidate).exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def resolve_crop_box(image_size: tuple[int, int], crop: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    if not crop:
        return None
    width, height = image_size
    left = max(0.0, min(1.0, float(crop.get("x", 0.0))))
    top = max(0.0, min(1.0, float(crop.get("y", 0.0))))
    crop_width = max(0.0, min(1.0 - left, float(crop.get("width", 0.0))))
    crop_height = max(0.0, min(1.0 - top, float(crop.get("height", 0.0))))
    if crop_width <= 0 or crop_height <= 0:
        return None
    x1 = int(round(left * width))
    y1 = int(round(top * height))
    x2 = int(round((left + crop_width) * width))
    y2 = int(round((top + crop_height) * height))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def queue_uploaded_files(job_dir: Path, uploaded_files: list[Any]) -> list[Path]:
    incoming_dir = job_dir / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    incoming_paths: list[Path] = []

    for index, file_storage in enumerate(
        sorted(uploaded_files, key=lambda item: natural_sort_key(Path(item.filename or ""))),
        start=1,
    ):
        filename = dedupe_name(incoming_dir, safe_filename(file_storage.filename, index))
        incoming_path = incoming_dir / filename
        file_storage.save(incoming_path)
        if incoming_path.suffix.lower() not in IMAGE_SUFFIXES:
            incoming_path.unlink(missing_ok=True)
            continue
        incoming_paths.append(incoming_path)

    return incoming_paths


def save_uploaded_images(
    job_dir: Path,
    incoming_paths: list[Path],
    crop: dict[str, Any] | None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    originals_dir = job_dir / "originals"
    inputs_dir = job_dir / "inputs"
    originals_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)

    saved_images: list[Path] = []
    original_meta: list[dict[str, Any]] = []

    for index, incoming_path in enumerate(sorted(incoming_paths, key=natural_sort_key), start=1):
        filename = dedupe_name(originals_dir, safe_filename(incoming_path.name, index))
        original_path = originals_dir / filename
        shutil.copy2(incoming_path, original_path)
        input_path = inputs_dir / filename
        if crop:
            with Image.open(original_path) as image:
                box = resolve_crop_box(image.size, crop)
                if box:
                    cropped = image.crop(box)
                    cropped.save(input_path)
                else:
                    image.save(input_path)
        else:
            shutil.copy2(original_path, input_path)

        saved_images.append(input_path)
        original_meta.append(
            {
                "name": filename,
                "original_url": f"/job-files/{job_dir.name}/originals/{filename}",
                "input_url": f"/job-files/{job_dir.name}/inputs/{filename}",
            }
        )

    return saved_images, original_meta


def build_result_payload(
    job_id: str,
    job_dir: Path,
    model_info: dict[str, Any],
    job_result: dict[str, Any],
    originals: list[dict[str, Any]],
) -> dict[str, Any]:
    original_map = {item["name"]: item for item in originals}
    pages: list[dict[str, Any]] = []

    for result in job_result["results"]:
        image_name = Path(result["image"]).name
        links = original_map.get(image_name, {})
        page = {
            "name": image_name,
            "status": result["status"],
            "summary": "",
            "global_notes": "",
            "items": [],
            "preview_url": links.get("original_url", ""),
            "translated_input_url": links.get("input_url", ""),
            "raw_url": f"/job-files/{job_id}/outputs/{Path(result['raw_path']).name}",
        }
        if result["status"] == "ok":
            data = result["data"]
            page["summary"] = data["page_summary"]
            page["global_notes"] = data["global_notes"]
            page["items"] = data["items"]
            page["json_url"] = f"/job-files/{job_id}/outputs/{Path(result['json_path']).name}"
            page["md_url"] = f"/job-files/{job_id}/outputs/{Path(result['md_path']).name}"
        pages.append(page)

    return {
        "job_id": job_id,
        "model": model_info["model"],
        "model_preset": model_info["model_preset"],
        "endpoint": model_info["endpoint"],
        "output_dir": str(job_dir / "outputs"),
        "failures": job_result["failures"],
        "pages": pages,
    }


def build_downloads(job_id: str, job_dir: Path) -> dict[str, str]:
    return {
        "zip": f"/downloads/{job_id}/package.zip",
        "markdown": f"/job-files/{job_id}/outputs/chapter_translation.md",
        "json": f"/job-files/{job_id}/outputs/chapter_translation.json",
        "csv": f"/job-files/{job_id}/outputs/chapter_translation.csv",
    }


def translate_job_worker(
    job_id: str,
    incoming_paths: list[Path],
    crop: dict[str, Any] | None,
    model_preset: str,
    start_if_needed: bool,
    timeout: int,
    max_tokens: int,
) -> None:
    job_dir = JOBS_DIR / job_id
    output_dir = job_dir / "outputs"
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        update_job(
            job_id,
            status="running",
            message="Checking local Qwen service...",
            progress={"current": 0, "total": len(incoming_paths), "current_name": ""},
        )

        model_info = ensure_model_online(model_preset, start_if_needed=start_if_needed, timeout=timeout)

        update_job(
            job_id,
            message="Preparing images...",
            settings={
                "model_preset": model_preset,
                "crop_enabled": bool(crop),
                "timeout": timeout,
                "max_tokens": max_tokens,
            },
        )
        saved_images, originals = save_uploaded_images(job_dir, incoming_paths, crop)
        if not saved_images:
            raise RuntimeError("No supported image files were uploaded.")

        def progress_callback(index: int, total: int, image_path: Path) -> None:
            update_job(
                job_id,
                message=f"Translating {image_path.name}...",
                progress={"current": index, "total": total, "current_name": image_path.name},
            )

        job_result = run_translation_job(
            images=saved_images,
            output_dir=output_dir,
            endpoint=model_info["endpoint"],
            model=model_info["model"],
            max_tokens=max_tokens,
            timeout=timeout,
            overwrite=True,
            progress_callback=progress_callback,
        )

        archive_base = job_dir / "package"
        archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=output_dir)
        result_payload = build_result_payload(job_id, job_dir, model_info, job_result, originals)
        downloads = build_downloads(job_id, job_dir)
        downloads["zip"] = f"/downloads/{job_id}/{Path(archive_path).name}"

        metadata = {
            "job": job_response(JOBS[job_id]),
            "result": result_payload,
            "downloads": downloads,
        }
        (job_dir / "job.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        update_job(
            job_id,
            status="done",
            message="Translation finished.",
            progress={"current": len(saved_images), "total": len(saved_images), "current_name": ""},
            result=result_payload,
            downloads=downloads,
            error="",
        )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            message="Translation failed.",
            error=str(exc),
        )


@app.get("/")
def index() -> Any:
    return render_template("index.html", default_preset=SERVER_OPTIONS["model_preset"])


@app.get("/api/status")
def api_status() -> Any:
    online = find_online_endpoint(timeout=3)
    return jsonify(
        {
            "online": online is not None,
            "active": online,
            "default_model_preset": SERVER_OPTIONS["model_preset"],
            "auto_start_model": SERVER_OPTIONS["auto_start_model"],
        }
    )


@app.post("/api/start-model")
def api_start_model() -> Any:
    payload = request.get_json(silent=True) or {}
    model_preset = str(payload.get("model_preset") or SERVER_OPTIONS["model_preset"])
    if model_preset not in {"7b", "30b"}:
        return jsonify({"ok": False, "error": "Invalid model preset."}), 400

    try:
        result = ensure_model_online(model_preset, start_if_needed=True, timeout=SERVER_OPTIONS["startup_timeout"])
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "active": result})


@app.post("/api/translate")
def api_translate() -> Any:
    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        return jsonify({"ok": False, "error": "No files were uploaded."}), 400

    crop_raw = request.form.get("crop_json", "").strip()
    try:
        crop = json.loads(crop_raw) if crop_raw else None
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "Invalid crop settings."}), 400
    model_preset = request.form.get("model_preset", SERVER_OPTIONS["model_preset"])
    start_if_needed = request.form.get("start_if_needed", "true").lower() != "false"
    timeout = int(request.form.get("timeout", SERVER_OPTIONS["startup_timeout"]))
    max_tokens = int(request.form.get("max_tokens", 4000))

    if model_preset not in {"7b", "30b"}:
        return jsonify({"ok": False, "error": "Invalid model preset."}), 400

    job_id = datetime.now().strftime("job-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    incoming_paths = queue_uploaded_files(job_dir, uploaded_files)
    if not incoming_paths:
        return jsonify({"ok": False, "error": "No supported image files were uploaded."}), 400

    with STATE_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "message": "Queued.",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "progress": {"current": 0, "total": len(incoming_paths), "current_name": ""},
            "downloads": {},
            "result": None,
            "error": "",
            "settings": {},
        }

    thread = threading.Thread(
        target=translate_job_worker,
        args=(job_id, incoming_paths, crop, model_preset, start_if_needed, timeout, max_tokens),
        daemon=True,
    )
    thread.start()

    return jsonify({"ok": True, "job_id": job_id})


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str) -> Any:
    with STATE_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"ok": False, "error": "Job not found."}), 404
        return jsonify({"ok": True, "job": job_response(job)})


@app.get("/job-files/<job_id>/<bucket>/<path:filename>")
def job_files(job_id: str, bucket: str, filename: str) -> Any:
    if bucket not in {"originals", "inputs", "outputs"}:
        abort(404)
    directory = JOBS_DIR / job_id / bucket
    if not directory.exists():
        abort(404)
    return send_from_directory(directory, filename, as_attachment=False)


@app.get("/downloads/<job_id>/<path:filename>")
def downloads(job_id: str, filename: str) -> Any:
    file_path = JOBS_DIR / job_id / filename
    if not file_path.exists():
        abort(404)
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local manga translation web app.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model-preset", choices=["7b", "30b"], default="7b")
    parser.add_argument("--startup-timeout", type=int, default=300)
    parser.add_argument("--auto-start-model", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    return parser.parse_args()


def maybe_auto_start_model() -> None:
    if not SERVER_OPTIONS["auto_start_model"]:
        return

    def background_start() -> None:
        try:
            ensure_model_online(
                SERVER_OPTIONS["model_preset"],
                start_if_needed=True,
                timeout=SERVER_OPTIONS["startup_timeout"],
            )
        except RuntimeError:
            return

    threading.Thread(target=background_start, daemon=True).start()


def maybe_open_browser(host: str, port: int) -> None:
    def open_page() -> None:
        webbrowser.open(f"http://{host}:{port}", new=1)

    threading.Timer(1.0, open_page).start()


def main() -> int:
    args = parse_args()
    set_server_options(args)
    maybe_auto_start_model()
    if args.open_browser:
        maybe_open_browser(args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
