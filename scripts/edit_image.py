#!/usr/bin/env python3
"""Edit images with the gpt-image-2 Images API fields."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid


CONFIG_PATH = Path("~/.config/image2-gen/config.json").expanduser()
CONFIG_EXAMPLE = '{"baseurl":"https://your-image-api.example.com/v1","token":"<api-token>","model":"gpt-image-2"}'
API_PATH = "/images/edits"
DEFAULT_OUTPUT_DIR = "image2_outputs"
DEFAULT_MODEL = "gpt-image-2"
ALLOWED_MODEL = "gpt-image-2"
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_BACKGROUND = ("auto", "opaque")
ALLOWED_QUALITY = ("auto", "low", "medium", "high")
ALLOWED_OUTPUT_FORMAT = ("png", "jpeg", "webp")
ALLOWED_MODERATION = ("auto", "low")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the gpt-image-2 image edits API and save returned images.")
    parser.add_argument("--api-key", "--token", dest="api_key", default=None, help="API token. Overrides config token.")
    parser.add_argument("--baseurl", default=None, help="API base URL. Overrides config baseurl.")
    parser.add_argument("--endpoint", default=None, help="Full API endpoint. Overrides baseurl.")
    parser.add_argument("--model", default=None, help="Must be gpt-image-2. Defaults to config model, then gpt-image-2.")
    parser.add_argument("--prompt", required=True, help="Edit prompt.")
    parser.add_argument("--image", required=True, action="append", help="Reference image path. Can be passed up to 16 times.")
    parser.add_argument("--mask", default=None, help="Optional mask image path.")
    parser.add_argument("--size", default="auto", help="Image size, for example auto, 1024x1024, 1536x1024.")
    parser.add_argument("--count", type=int, default=1, help="Number of images to request.")
    parser.add_argument("--quality", choices=ALLOWED_QUALITY, default="auto", help="Rendering quality.")
    parser.add_argument("--background", choices=ALLOWED_BACKGROUND, default="auto", help="Background handling.")
    parser.add_argument("--output-format", choices=ALLOWED_OUTPUT_FORMAT, default="png", help="Saved image format.")
    parser.add_argument("--output-compression", type=int, default=None, help="0-100 compression for jpeg/webp only.")
    parser.add_argument("--moderation", choices=ALLOWED_MODERATION, default="auto", help="Moderation strictness.")
    parser.add_argument("--user", default=None, help="Optional end-user identifier.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for images and response.json.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Request timeout in seconds.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


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
    model = str(args.model or config.get("model") or DEFAULT_MODEL).strip()
    if model != ALLOWED_MODEL:
        fail(f"only {ALLOWED_MODEL} is supported by this script.")
    return model


def check_size(size: str) -> None:
    if size == "auto":
        return
    match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not match:
        fail("--size must be auto or WIDTHxHEIGHT, for example 1024x1024.")
    width, height = (int(match.group(1)), int(match.group(2)))
    if width % 16 or height % 16:
        fail("--size width and height must be multiples of 16 for gpt-image-2.")
    if max(width, height) > 3840:
        fail("--size maximum edge must be <= 3840 for gpt-image-2.")
    if max(width, height) / min(width, height) > 3:
        fail("--size long edge to short edge ratio must not exceed 3:1.")
    pixels = width * height
    if pixels < 655_360 or pixels > 8_294_400:
        fail("--size total pixels must be between 655,360 and 8,294,400.")


def check_image_path(raw_path: str, label: str) -> Path:
    path = Path(raw_path)
    if not path.exists():
        fail(f"{label} does not exist: {path}")
    if not path.is_file():
        fail(f"{label} is not a file: {path}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        fail(f"{label} must be PNG, JPEG, or WebP.")
    return path


def check_args(args: argparse.Namespace, endpoint: str, model: str) -> tuple[list[Path], Path | None]:
    if not endpoint.strip():
        fail("endpoint is required.")
    if model != ALLOWED_MODEL:
        fail(f"only {ALLOWED_MODEL} is supported.")
    if not args.prompt.strip():
        fail("--prompt is required.")
    if args.count < 1:
        fail("--count must be at least 1.")
    if len(args.image) > 16:
        fail("gpt-image-2 supports at most 16 input images.")
    check_size(args.size)
    if args.output_compression is not None:
        if args.output_format not in {"jpeg", "webp"}:
            fail("--output-compression is only valid with --output-format jpeg or webp.")
        if args.output_compression < 0 or args.output_compression > 100:
            fail("--output-compression must be between 0 and 100.")

    image_paths = [check_image_path(path, "image") for path in args.image]
    mask_path = check_image_path(args.mask, "mask") if args.mask else None
    return image_paths, mask_path


def add_field(chunks: list[bytes], boundary: str, name: str, value: str) -> None:
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
    chunks.append(value.encode("utf-8"))
    chunks.append(b"\r\n")


def add_file(chunks: list[bytes], boundary: str, field_name: str, file_path: Path) -> None:
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")


def build_multipart(fields: dict[str, str], image_paths: list[Path], mask_path: Path | None) -> tuple[bytes, str]:
    boundary = f"----image2-gen-skill-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        add_field(chunks, boundary, name, value)
    for image_path in image_paths:
        add_file(chunks, boundary, "image[]", image_path)
    if mask_path:
        add_file(chunks, boundary, "mask", mask_path)

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
        print_response_error(exc.code, exc.read(), elapsed)
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
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return suffix
    return ".png"


def download_url(url: str, output_path: Path, timeout: float) -> None:
    request = Request(url, headers={"User-Agent": "image2-gen-skill/1.0"})
    with urlopen(request, timeout=timeout) as response:
        output_path.write_bytes(response.read())


def save_outputs(data: dict[str, Any], output_dir: Path, output_format: str, timeout: float) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "response.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    items = data.get("data")
    if not isinstance(items, list):
        fail("response does not contain a data array.")

    saved: list[Path] = []
    suffix = ".jpg" if output_format == "jpeg" else f".{output_format}"
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            path = output_dir / f"image_{index}{suffix}"
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
    model = get_model(args, config)
    image_paths, mask_path = check_args(args, endpoint, model)

    fields = {
        "model": model,
        "prompt": args.prompt,
        "size": args.size,
        "n": str(args.count),
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "moderation": args.moderation,
    }
    if args.output_compression is not None:
        fields["output_compression"] = str(args.output_compression)
    if args.user:
        fields["user"] = args.user

    body, boundary = build_multipart(fields, image_paths, mask_path)
    data, elapsed = request_multipart(endpoint, api_key, body, boundary, args.timeout)
    saved = save_outputs(data, Path(args.output_dir), args.output_format, args.timeout)
    print(json.dumps({
        "ok": True,
        "elapsed_seconds": round(elapsed, 3),
        "model": model,
        "output_dir": str(Path(args.output_dir).resolve()),
        "saved_files": [str(path.resolve()) for path in saved],
        "response_file": str((Path(args.output_dir) / "response.json").resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
