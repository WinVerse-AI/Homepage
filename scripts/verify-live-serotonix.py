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
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ASSETS = {
    "assets/serotonix-mask-hero-2026.webp": (2200, 1524),
    "assets/serotonix-layered-architecture-2026.webp": (1536, 1024),
    "assets/serotonix-product-cad-2026.webp": (1448, 1086),
    "assets/serotonix-product-dimensions-2026.webp": (1448, 1086),
    "assets/serotonix-controller-pcba-2026.webp": (2200, 2136),
    "assets/serotonix-system-architecture-2026.webp": (1448, 1086),
    "assets/serotonix-system-control-2026.webp": (1448, 1086),
    "assets/serotonix-colour-finish-2026.webp": (1511, 2200),
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

    page_attempts: list[str] = []
    page_ok = False
    for attempt in range(1, args.attempts + 1):
        try:
            status, headers, html_bytes = fetch(page_url)
            html = html_bytes.decode("utf-8")
            content_type = headers.get("content-type", "")
            page_parser = ImageParser()
            page_parser.feed(html)
            sources = set(page_parser.sources)
            page_ok = status == 200 and "text/html" in content_type.lower() and sources == set(ASSETS)
            report["page"] = {
                "status": status,
                "content_type": content_type,
                "bytes": len(html_bytes),
                "sha256": hashlib.sha256(html_bytes).hexdigest(),
                "image_references": sorted(sources),
                "attempt": attempt,
                "retry_errors": page_attempts,
            }
            if page_ok:
                break
            page_attempts.append(f"attempt {attempt}: stale or unexpected page content")
        except Exception as exc:
            page_attempts.append(f"attempt {attempt}: {exc}")
        if attempt < args.attempts:
            time.sleep(args.delay)
    if not page_ok:
        failures.append(f"page did not converge to expected deployment: {'; '.join(page_attempts)}")

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
        asset_attempts: list[str] = []
        asset_ok = False
        for attempt in range(1, args.attempts + 1):
            try:
                status, headers, body = fetch(asset_url)
                content_type = headers.get("content-type", "")
                dimensions = webp_dimensions(body)
                live_sha = hashlib.sha256(body).hexdigest()
                asset_ok = (
                    status == 200
                    and "image/webp" in content_type.lower()
                    and dimensions == expected_dimensions
                    and live_sha == local_sha
                )
                item.update({
                    "status": status,
                    "content_type": content_type,
                    "live_bytes": len(body),
                    "live_sha256": live_sha,
                    "dimensions": list(dimensions),
                    "attempt": attempt,
                    "retry_errors": asset_attempts,
                    "matches_commit": live_sha == local_sha,
                })
                if asset_ok:
                    break
                asset_attempts.append(f"attempt {attempt}: stale or unexpected asset bytes")
            except Exception as exc:
                asset_attempts.append(f"attempt {attempt}: {exc}")
            if attempt < args.attempts:
                time.sleep(args.delay)
        if not asset_ok:
            item["error"] = "; ".join(asset_attempts)
            failures.append(f"{relative}: did not converge to committed bytes")
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
