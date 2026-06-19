#!/usr/bin/env python3
"""Edit/generate images from a reference image through the router image edits API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid


CONFIG_PATH = Path("~/.config/image2-gen/config.json").expanduser()
CONFIG_EXAMPLE = '{"baseurl":"https://your-image-api.example.com/v1","token":"<api-token>"}'
API_PATH = "/images/edits"
DEFAULT_OUTPUT_DIR = "image2_outputs"
DEFAULT_MODEL = "gpt-image-2"
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the image edit API and save returned images.")
    parser.add_argument("--api-key", "--token", dest="api_key", default=None, help="API token. Overrides config token.")
    parser.add_argument("--baseurl", default=None, help="API base URL. Overrides config baseurl.")
    parser.add_argument("--endpoint", default=None, help="Full API endpoint. Overrides baseurl.")
    parser.add_argument("--model", default=None, help="Image model name. Defaults to config model, then gpt-image-2.")
    parser.add_argument("--prompt", required=True, help="Edit prompt.")
    parser.add_argument("--image", required=True, help="Reference image path.")
    parser.add_argument("--image-field-name", default="image", help="Multipart file field name.")
    parser.add_argument("--size", default="1024x1024", help="Image size, for example 1024x1024.")
    parser.add_argument("--count", type=int, default=1, help="Number of images to request.")
    parser.add_argument("--extra-json", default="{}", help="JSON object appended as multipart fields.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for images and response.json.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Request timeout in seconds.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_extra_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        fail(f"--extra-json is not valid JSON: {exc}")
    if not isinstance(value, dict):
        fail("--extra-json must be a JSON object.")
    return value


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"config file is not valid JSON: {CONFIG_PATH} ({exc})")
    if not isinstance(value, dict):
        fail(f"config file must contain a JSON object: {CONFIG_PATH}")
    return value


def get_api_key(explicit: str | None, config: dict[str, Any]) -> str:
    key = explicit or config.get("token") or os.environ.get("XFOUR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        return str(key)
    if not CONFIG_PATH.exists():
        fail(
            f"missing config file: {CONFIG_PATH}\n"
            f"create it with JSON like: {CONFIG_EXAMPLE}\n"
            "or pass --api-key/--token for this run."
        )
    fail(
        f"missing token in config file: {CONFIG_PATH}\n"
        f"expected JSON like: {CONFIG_EXAMPLE}\n"
        "or pass --api-key/--token for this run."
    )


def get_endpoint(args: argparse.Namespace, config: dict[str, Any]) -> str:
    if args.endpoint:
        return args.endpoint.strip()
    baseurl = args.baseurl or config.get("baseurl")
    if not baseurl:
        fail(
            f"missing baseurl in config file: {CONFIG_PATH}\n"
            f"expected JSON like: {CONFIG_EXAMPLE}\n"
            "or pass --baseurl for this run."
        )
    return f"{str(baseurl).rstrip('/')}{API_PATH}"

def get_model(args: argparse.Namespace, config: dict[str, Any]) -> str:
    model = args.model or config.get("model") or DEFAULT_MODEL
    model = str(model).strip()
    if not model:
        fail("image model is empty. Set config model or pass --model.")
    return model
def check_args(args: argparse.Namespace, endpoint: str) -> Path:
    if not endpoint.strip():
        fail("endpoint is required.")
    if not args.model.strip():
        fail("--model is required.")
    if not args.prompt.strip():
        fail("--prompt is required.")
    if not args.image_field_name.strip():
        fail("--image-field-name is required.")
    if args.count < 1:
        fail("--count must be at least 1.")

    image_path = Path(args.image)
    if not image_path.exists():
        fail(f"image does not exist: {image_path}")
    if not image_path.is_file():
        fail(f"image is not a file: {image_path}")
    if image_path.suffix.lower() not in ALLOWED_SUFFIXES:
        fail("image must be PNG, JPEG, or WebP.")
    return image_path


def normalize_field_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_multipart(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----image2-gen-skill-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def request_multipart(endpoint: str, api_key: str, body: bytes, boundary: str, timeout: float) -> tuple[dict[str, Any], float]:
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    start = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        elapsed = time.perf_counter() - start
        raw = exc.read()
        print_response_error(exc.code, raw, elapsed)
        raise SystemExit(1)
    except URLError as exc:
        elapsed = time.perf_counter() - start
        fail(f"request failed after {elapsed:.3f}s: {exc.reason}")
    elapsed = time.perf_counter() - start
    return decode_json(raw), elapsed


def decode_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        fail("response is not valid UTF-8.")
    except json.JSONDecodeError as exc:
        fail(f"response is not valid JSON: {exc}")
    if not isinstance(value, dict):
        fail("response JSON is not an object.")
    return value


def print_response_error(status: int, raw: bytes, elapsed: float) -> None:
    try:
        data = json.loads(raw.decode("utf-8"))
        rendered = json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        rendered = raw.decode("utf-8", errors="replace")
    print(f"HTTP {status} after {elapsed:.3f}s", file=sys.stderr)
    print(rendered, file=sys.stderr)


def extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return suffix
    guessed = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "")
    return guessed or ".png"


def download_url(url: str, output_path: Path, timeout: float) -> None:
    request = Request(url, headers={"User-Agent": "image2-gen-skill/1.0"})
    with urlopen(request, timeout=timeout) as response:
        output_path.write_bytes(response.read())


def save_outputs(data: dict[str, Any], output_dir: Path, timeout: float) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "response.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    items = data.get("data")
    if not isinstance(items, list):
        fail("response does not contain a data array.")

    saved: list[Path] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            path = output_dir / f"image_{index}.png"
            path.write_bytes(base64.b64decode(item["b64_json"]))
            saved.append(path)
        elif item.get("url"):
            ext = extension_from_url(str(item["url"]))
            path = output_dir / f"image_{index}{ext}"
            download_url(str(item["url"]), path, timeout)
            saved.append(path)
    return saved


def main() -> None:
    args = parse_args()
    config = load_config()
    endpoint = get_endpoint(args, config)
    api_key = get_api_key(args.api_key, config)
    image_path = check_args(args, endpoint)
    extra = load_extra_json(args.extra_json)

    fields = {
        "model": get_model(args, config),
        "prompt": args.prompt,
        "size": args.size,
        "n": str(args.count),
    }
    fields.update({key: normalize_field_value(value) for key, value in extra.items()})

    body, boundary = build_multipart(fields, args.image_field_name, image_path)
    data, elapsed = request_multipart(endpoint, api_key, body, boundary, args.timeout)
    saved = save_outputs(data, Path(args.output_dir), args.timeout)
    print(json.dumps({
        "ok": True,
        "elapsed_seconds": round(elapsed, 3),
        "output_dir": str(Path(args.output_dir).resolve()),
        "saved_files": [str(path.resolve()) for path in saved],
        "response_file": str((Path(args.output_dir) / "response.json").resolve()),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
