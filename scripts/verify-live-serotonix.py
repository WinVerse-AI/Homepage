#!/usr/bin/env python3
"""Verify the deployed SerotoniX page and assets against the checked-out commit."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ASSETS = {
    "assets/serotonix-mask-hero-2026.webp": (1200, 900),
    "assets/serotonix-layered-architecture-2026.webp": (1536, 1024),
    "assets/serotonix-product-cad-2026.webp": (1448, 1086),
    "assets/serotonix-product-dimensions-2026.webp": (1448, 1086),
    "assets/serotonix-controller-pcba-2026.webp": (1536, 1024),
    "assets/serotonix-system-architecture-2026.webp": (1448, 1086),
    "assets/serotonix-system-control-2026.webp": (1448, 1086),
    "assets/serotonix-colour-finish-2026.webp": (1024, 1536),
}


def webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a RIFF/WebP file")
    chunk = data[12:16]
    if chunk == b"VP8X":
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    if chunk == b"VP8L":
        if data[20] != 0x2F:
            raise ValueError("invalid VP8L signature")
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        marker = data.find(b"\x9d\x01\x2a", 20, 40)
        if marker < 0:
            raise ValueError("VP8 frame header not found")
        width, height = struct.unpack_from("<HH", data, marker + 3)
        return width & 0x3FFF, height & 0x3FFF
    raise ValueError(f"unsupported WebP chunk {chunk!r}")


class ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        src = values.get("src") or ""
        if "serotonix-" in src:
            self.sources.append(urlsplit(src).path.lstrip("/"))


def fetch(url: str, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
    request = Request(url, headers={"User-Agent": "WinVerse-SerotoniX-Deployment-Check/1.0", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=timeout) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        return response.status, headers, response.read()


def fetch_with_retry(url: str, attempts: int, delay: int) -> tuple[int, dict[str, str], bytes, list[str]]:
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            status, headers, body = fetch(url)
            if status == 200:
                return status, headers, body, errors
            errors.append(f"attempt {attempt}: HTTP {status}")
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append(f"attempt {attempt}: {exc}")
        if attempt < attempts:
            time.sleep(delay)
    raise RuntimeError("; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--attempts", type=int, default=18)
    parser.add_argument("--delay", type=int, default=10)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    base_url = args.base_url.rstrip("/") + "/"
    page_url = urljoin(base_url, "serotonix.html")
    report: dict[str, object] = {
        "base_url": base_url,
        "page_url": page_url,
        "commit_sha": __import__("os").environ.get("GITHUB_SHA", "local"),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "page": {},
        "assets": [],
        "passed": False,
    }
    failures: list[str] = []

    try:
        status, headers, html_bytes, retry_errors = fetch_with_retry(page_url, args.attempts, args.delay)
        html = html_bytes.decode("utf-8")
        content_type = headers.get("content-type", "")
        report["page"] = {
            "status": status,
            "content_type": content_type,
            "bytes": len(html_bytes),
            "sha256": hashlib.sha256(html_bytes).hexdigest(),
            "retry_errors": retry_errors,
        }
        if "text/html" not in content_type.lower():
            failures.append(f"page content type is {content_type!r}, expected text/html")
        page_parser = ImageParser()
        page_parser.feed(html)
        if set(page_parser.sources) != set(ASSETS):
            failures.append(f"live image reference set mismatch: {sorted(set(page_parser.sources))}")
    except Exception as exc:
        failures.append(f"page request failed: {exc}")

    for relative, expected_dimensions in ASSETS.items():
        local_path = root / relative
        local_bytes = local_path.read_bytes()
        local_sha = hashlib.sha256(local_bytes).hexdigest()
        asset_url = urljoin(base_url, relative)
        item: dict[str, object] = {
            "relative_path": relative,
            "url": asset_url,
            "expected_dimensions": list(expected_dimensions),
            "local_bytes": len(local_bytes),
            "local_sha256": local_sha,
        }
        try:
            status, headers, body, retry_errors = fetch_with_retry(asset_url, args.attempts, args.delay)
            content_type = headers.get("content-type", "")
            dimensions = webp_dimensions(body)
            live_sha = hashlib.sha256(body).hexdigest()
            item.update({
                "status": status,
                "content_type": content_type,
                "live_bytes": len(body),
                "live_sha256": live_sha,
                "dimensions": list(dimensions),
                "retry_errors": retry_errors,
                "matches_commit": live_sha == local_sha,
            })
            if "image/webp" not in content_type.lower():
                failures.append(f"{relative}: content type {content_type!r}")
            if dimensions != expected_dimensions:
                failures.append(f"{relative}: dimensions {dimensions}, expected {expected_dimensions}")
            if live_sha != local_sha:
                failures.append(f"{relative}: deployed bytes do not match commit")
        except Exception as exc:
            item["error"] = str(exc)
            failures.append(f"{relative}: {exc}")
        cast_assets = report["assets"]
        assert isinstance(cast_assets, list)
        cast_assets.append(item)

    report["failures"] = failures
    report["passed"] = not failures
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1
    print(f"Verified live page and {len(ASSETS)} production image assets at {base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
