from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

# English prompts (default - more stable with Qwen-VL)
SYSTEM_PROMPT_EN = """You are a professional manga translator specializing in context-aware Chinese localization.

IMPORTANT:
1. Detect ALL text in the image - Japanese, English, Chinese, Korean, or ANY language
2. Look at the ENTIRE image to understand scene, characters, and mood
3. Identify character relationships from visual cues

Translation rules:
- Translate ALL detected text to Simplified Chinese
- For Japanese: adapt to natural Chinese, preserve tone
- For English: translate to Chinese naturally
- For other languages: translate to Chinese
- 对白要像动漫台词，有角色个性
- 语气要符合角色表情和场景

Output rules:
- Output in reading order
- Merge sentences in same bubble
- If no text detected, return empty items array
- Only output JSON, no markdown"""

USER_PROMPT_EN = """Task: Detect and translate ALL text in this manga to Chinese.

First understand the scene:
- What language is the text?
- Who are the characters?
- What's the mood?

Translate each text bubble to Chinese with appropriate tone.

Output JSON:
{
  "page_summary": "中文场景概括",
  "items": [
    {"id": "1", "type": "dialogue", "source_jp": "检测到的原文(任何语言)", "target_zh": "中文翻译", "notes": "角色语气"}
  ],
  "global_notes": "场景语境"
}

IMPORTANT: Translate ANY language detected, not just Japanese!"""

# Chinese prompts (fallback)
SYSTEM_PROMPT_ZH = """你是专业的日文漫画汉化助手。
你的任务是识别漫画页面中的日文文本，并翻译成自然、准确、适合漫画对白的简体中文。

请严格遵守这些规则：
1. 只处理图片里实际存在的文字，不要脑补没有出现的内容。
2. 按阅读顺序输出，同一个气泡里的多句可以合并。
3. 对白使用自然口语，保留角色语气；旁白、标题、注释保持对应文体。
4. 拟声词和效果音也要识别；如果不建议直接翻成中文，请在 notes 里说明。
5. 看不清的地方明确写成 [不清楚]，不要捏造。
6. 如果图片里没有可辨认的日文文字，必须返回空的 items 数组，不要编造对白。
7. 只输出 JSON 对象，不要输出 Markdown，不要输出代码块。"""

USER_PROMPT_ZH = """请把这页漫画整理成以下 JSON 结构：
{
  "page_summary": "用一句中文概括本页内容；如果没有可辨认文字，写 未识别到可翻译文本",
  "items": [
    {
      "id": "1",
      "type": "dialogue|narration|caption|sfx|other",
      "source_jp": "识别出的日文原文，不清楚时写 [不清楚]",
      "target_zh": "对应的简体中文汉化稿",
      "notes": "可选；语气、双关、拟声词处理说明，没有就留空"
    }
  ],
  "global_notes": "整页级别的说明，没有就留空"
}

请注意：
- 输出必须是合法 JSON。
- items 必须按阅读顺序排列。
- 如果图片中没有可辨认日文，请返回 items: []。
- 不要额外解释。"""

# Default to English for stability (Qwen-VL has encoding issues with non-English prompts)
SYSTEM_PROMPT = SYSTEM_PROMPT_EN
USER_PROMPT = USER_PROMPT_EN


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use a local Qwen-VL OpenAI-compatible endpoint to translate manga pages."
    )
    parser.add_argument("input_path", help="Image file or a folder containing manga page images.")
    parser.add_argument(
        "--output-dir",
        help="Directory for generated markdown/json/csv files. Defaults next to the input.",
    )
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8001/v1",
        help="Base API URL. Examples: http://127.0.0.1:8001/v1 or http://127.0.0.1:8000/v1",
    )
    parser.add_argument(
        "--model",
        help="Model name served by vLLM. If omitted, the script will call /v1/models and use the first model.",
    )
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature.")
    parser.add_argument("--max-tokens", type=int, default=1800, help="Maximum output tokens per page.")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout in seconds.")
    parser.add_argument("--limit", type=int, help="Only process the first N images after sorting.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing output folder.")
    return parser.parse_args()


def normalize_endpoint(raw: str) -> str:
    endpoint = raw.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    return endpoint


def natural_sort_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", path.name.lower())
    key: list[Any] = []
    for part in parts:
        key.append(int(part) if part.isdigit() else part)
    return key


def gather_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
    images = [path for path in input_path.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES]
    return sorted(images, key=natural_sort_key)


def default_output_dir(input_path: Path) -> Path:
    if input_path.is_file():
        return input_path.parent / f"{input_path.stem}_translation"
    return input_path.parent / f"{input_path.name}_translation"


def read_json(url: str, timeout: int) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_model(endpoint: str, timeout: int) -> str:
    data = read_json(f"{endpoint}/models", timeout)
    models = data.get("data") or []
    if not models:
        raise RuntimeError(f"No models were returned by {endpoint}/models")
    model_id = models[0].get("id")
    if not model_id:
        raise RuntimeError(f"Model metadata from {endpoint}/models does not include an id")
    return str(model_id)


def encode_image_as_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    mime_type = mime_type or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def request_translation(
    endpoint: str,
    model: str,
    image_path: Path,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": encode_image_as_data_url(image_path)}},
                ],
            },
        ],
    }
    data = post_json(f"{endpoint}/chat/completions", payload, timeout)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("No choices were returned by the model.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("The model response did not include message.content.")
    return str(content)


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    attempts = [raw_text.strip()]
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, flags=re.DOTALL)
    attempts.extend(fenced)

    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        attempts.append(raw_text[first_brace : last_brace + 1])

    for candidate in attempts:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    raise ValueError("The model response was not valid JSON.")


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = str(payload.get("page_summary") or "").strip()
    global_notes = str(payload.get("global_notes") or "").strip()
    normalized_items: list[dict[str, str]] = []

    for index, item in enumerate(payload.get("items") or [], start=1):
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "id": str(item.get("id") or index),
                "type": str(item.get("type") or "other").strip() or "other",
                "source_jp": str(item.get("source_jp") or item.get("jp") or "").strip(),
                "target_zh": str(item.get("target_zh") or item.get("zh") or item.get("translation") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
            }
        )

    return {
        "page_summary": summary,
        "global_notes": global_notes,
        "items": normalized_items,
    }


def markdown_cell(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("|", "\\|")
    return cleaned.replace("\n", "<br>")


def build_page_markdown(image_path: Path, payload: dict[str, Any]) -> str:
    lines = [f"## {image_path.name}", ""]
    lines.append(f"- 原图: `{image_path}`")
    lines.append(f"- 内容概括: {payload['page_summary'] or '（空）'}")
    lines.append(f"- 整页备注: {payload['global_notes'] or '（无）'}")
    lines.append("")
    lines.append("| 序号 | 类型 | 日文原文 | 中文汉化 | 备注 |")
    lines.append("| --- | --- | --- | --- | --- |")

    for item in payload["items"]:
        lines.append(
            "| {id} | {type} | {source_jp} | {target_zh} | {notes} |".format(
                id=markdown_cell(item["id"]),
                type=markdown_cell(item["type"]),
                source_jp=markdown_cell(item["source_jp"] or "（空）"),
                target_zh=markdown_cell(item["target_zh"] or "（空）"),
                notes=markdown_cell(item["notes"] or "（无）"),
            )
        )

    if not payload["items"]:
        lines.append("| - | - | （未识别到文字） | （无） | （无） |")

    lines.append("")
    return "\n".join(lines)


def ensure_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory already exists and is not empty: {output_dir}\n"
            "Use --overwrite or choose a different --output-dir."
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def write_outputs(
    output_dir: Path,
    image_path: Path,
    raw_response: str,
    normalized_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    stem = image_path.stem
    raw_path = output_dir / f"{stem}.raw.txt"
    raw_path.write_text(raw_response, encoding="utf-8")

    if normalized_payload is None:
        return {
            "image": str(image_path),
            "status": "raw_only",
            "raw_path": str(raw_path),
        }

    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(normalized_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_page_markdown(image_path, normalized_payload), encoding="utf-8")
    return {
        "image": str(image_path),
        "status": "ok",
        "raw_path": str(raw_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "data": normalized_payload,
    }


def write_summary_files(output_dir: Path, model: str, results: list[dict[str, Any]]) -> None:
    summary_md = output_dir / "chapter_translation.md"
    summary_json = output_dir / "chapter_translation.json"
    summary_csv = output_dir / "chapter_translation.csv"

    md_lines = [
        "# 漫画汉化整理",
        "",
        f"- 模型: `{model}`",
        f"- 页数: `{len(results)}`",
        "",
    ]

    json_payload: dict[str, Any] = {"model": model, "pages": []}
    csv_rows: list[dict[str, str]] = []

    for result in results:
        image_name = Path(result["image"]).name
        if result["status"] != "ok":
            md_lines.extend(
                [
                    f"## {image_name}",
                    "",
                    f"- 状态: 仅保留原始回复，未成功解析 JSON",
                    f"- 原始回复: `{result['raw_path']}`",
                    "",
                ]
            )
            json_payload["pages"].append(result)
            continue

        page_data = result["data"]
        json_payload["pages"].append(
            {
                "image": result["image"],
                "page_summary": page_data["page_summary"],
                "global_notes": page_data["global_notes"],
                "items": page_data["items"],
            }
        )
        md_lines.append(build_page_markdown(Path(result["image"]), page_data))

        for item in page_data["items"]:
            csv_rows.append(
                {
                    "image": image_name,
                    "id": item["id"],
                    "type": item["type"],
                    "source_jp": item["source_jp"],
                    "target_zh": item["target_zh"],
                    "notes": item["notes"],
                }
            )

    summary_md.write_text("\n".join(md_lines), encoding="utf-8")
    summary_json.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with summary_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["image", "id", "type", "source_jp", "target_zh", "notes"],
        )
        writer.writeheader()
        writer.writerows(csv_rows)


def translate_single_image(
    image_path: Path,
    output_dir: Path,
    endpoint: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> tuple[dict[str, Any], bool]:
    try:
        raw_response = request_translation(
            endpoint=endpoint,
            model=model,
            image_path=image_path,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        try:
            normalized_payload = normalize_payload(extract_json_payload(raw_response))
            had_failure = False
        except ValueError:
            normalized_payload = None
            had_failure = True
        return write_outputs(output_dir, image_path, raw_response, normalized_payload), had_failure
    except (RuntimeError, HTTPError, URLError, TimeoutError) as exc:
        error_text = f"REQUEST_FAILED: {exc}"
        return write_outputs(output_dir, image_path, error_text, None), True


def run_translation_job(
    images: list[Path],
    output_dir: Path,
    endpoint: str,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: int = 180,
    overwrite: bool = False,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    normalized_endpoint = normalize_endpoint(endpoint)
    ensure_output_dir(output_dir, overwrite=overwrite)
    resolved_model = model or detect_model(normalized_endpoint, timeout)

    results: list[dict[str, Any]] = []
    failures = 0

    for index, image_path in enumerate(images, start=1):
        if progress_callback is not None:
            progress_callback(index, len(images), image_path)
        result, had_failure = translate_single_image(
            image_path=image_path,
            output_dir=output_dir,
            endpoint=normalized_endpoint,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if had_failure:
            failures += 1
        results.append(result)

    write_summary_files(output_dir, resolved_model, results)
    return {
        "endpoint": normalized_endpoint,
        "model": resolved_model,
        "images": [str(path) for path in images],
        "output_dir": str(output_dir),
        "results": results,
        "failures": failures,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args()
    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_output_dir(input_path)
    endpoint = normalize_endpoint(args.endpoint)

    def format_connection_error(exc: Exception, endpoint: str) -> str:
        """将连接错误转换为用户友好的中文提示"""
        import re
        err_str = str(exc)
        # 检测常见连接错误
        if "10061" in err_str or "111" in err_str or "refused" in err_str.lower() or "无法连接" in err_str:
            # 从 endpoint 提取端口
            port_match = re.search(r":(\d+)/", endpoint)
            port = port_match.group(1) if port_match else "8001/8000"
            return (
                f"无法连接到本地 Qwen-VL 服务 (尝试访问 {endpoint})。\n\n"
                "请检查以下事项：\n"
                "1. WSL (Ubuntu) 是否已启动: `wsl -d Ubuntu -l -v`\n"
                f"2. vLLM 服务是否正在运行 (端口 {port})\n"
                "3. 启动脚本是否存在: `wsl -d Ubuntu -e bash -lc \"test -f ~/workspace/start_vllm.sh && echo exists\"`\n"
                "4. 如需手动启动: `wsl -d Ubuntu -e bash -lc \"~/workspace/start_vllm.sh 7b\"`\n\n"
                f"原始错误: {exc}"
            )
        return str(exc)

    try:
        images = gather_images(input_path)
        if args.limit:
            images = images[: args.limit]
        if not images:
            raise FileNotFoundError(f"No supported images were found in {input_path}")
    except (FileNotFoundError, FileExistsError, RuntimeError, HTTPError, URLError) as exc:
        print(f"[error] {format_connection_error(exc, endpoint)}", file=sys.stderr)
        return 1

    try:
        job = run_translation_job(
            images=images,
            output_dir=output_dir,
            endpoint=endpoint,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            overwrite=args.overwrite,
            progress_callback=lambda index, total, image_path: print(
                f"[{index}/{total}] Translating {image_path.name} ..."
            ),
        )
    except (FileExistsError, RuntimeError, HTTPError, URLError) as exc:
        print(f"[error] {format_connection_error(exc, endpoint)}", file=sys.stderr)
        return 1

    print(f"[info] endpoint: {job['endpoint']}")
    print(f"[info] model: {job['model']}")
    print(f"[info] images: {len(images)}")
    print(f"[info] output: {output_dir}")
    print("")
    print(f"[done] Results saved to: {output_dir}")
    print(f"[done] Summary markdown: {output_dir / 'chapter_translation.md'}")
    if job["failures"]:
        print(f"[done] Pages with manual follow-up needed: {job['failures']}")
    else:
        print("[done] All pages produced structured outputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
