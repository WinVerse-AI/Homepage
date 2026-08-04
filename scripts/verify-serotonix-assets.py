#!/usr/bin/env python3
"""Fail fast when the SerotoniX gallery contains missing or malformed image assets."""
from __future__ import annotations

import argparse
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED = {
    "assets/serotonix-mask-hero-2026.webp": (1200, 900),
    "assets/serotonix-layered-architecture-2026.webp": (1536, 1024),
    "assets/serotonix-product-cad-2026.webp": (1448, 1086),
    "assets/serotonix-product-dimensions-2026.webp": (1448, 1086),
    "assets/serotonix-controller-pcba-2026.webp": (1536, 1024),
    "assets/serotonix-system-architecture-2026.webp": (1448, 1086),
    "assets/serotonix-system-control-2026.webp": (1448, 1086),
    "assets/serotonix-colour-finish-2026.webp": (1024, 1536),
}
GALLERY = set(EXPECTED) - {"assets/serotonix-mask-hero-2026.webp"}


def webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a RIFF/WebP file")
    chunk = data[12:16]
    if chunk == b"VP8X":
        return (1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little"))
    if chunk == b"VP8L":
        if data[20] != 0x2F:
            raise ValueError("invalid VP8L signature")
        bits = int.from_bytes(data[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8 ":
        marker = data.find(b"\x9d\x01\x2a", 20, 40)
        if marker < 0:
            raise ValueError("VP8 frame header not found")
        width, height = struct.unpack_from("<HH", data, marker + 3)
        return (width & 0x3FFF, height & 0x3FFF)
    raise ValueError(f"unsupported WebP chunk {chunk!r}")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: (v or "") for k, v in attrs}
        if tag == "img":
            self.images.append(values)
        elif tag == "a":
            self.links.append(values)


def local_path(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    html_path = root / "serotonix.html"
    errors: list[str] = []

    if not html_path.is_file():
        print(f"ERROR: missing {html_path}", file=sys.stderr)
        return 1

    page = PageParser()
    page.feed(html_path.read_text(encoding="utf-8"))
    referenced = [local_path(item.get("src", "")) for item in page.images if "serotonix-" in item.get("src", "")]

    if set(referenced) != set(EXPECTED):
        errors.append(f"SerotoniX image set mismatch: expected {sorted(EXPECTED)}, found {sorted(set(referenced))}")
    duplicates = sorted({item for item in referenced if referenced.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate image references: {duplicates}")

    actual_names = {p.name for p in (root / "assets").iterdir() if p.is_file()}
    for relative, expected_size in EXPECTED.items():
        asset = root / relative
        if asset.name not in actual_names:
            errors.append(f"case-sensitive asset name missing: {relative}")
            continue
        if not asset.is_file():
            errors.append(f"missing asset: {relative}")
            continue
        data = asset.read_bytes()
        if not data:
            errors.append(f"zero-byte asset: {relative}")
            continue
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            errors.append(f"Git LFS pointer committed instead of image: {relative}")
            continue
        try:
            dimensions = webp_dimensions(data)
        except ValueError as exc:
            errors.append(f"cannot decode {relative}: {exc}")
            continue
        if dimensions != expected_size:
            errors.append(f"dimension mismatch for {relative}: expected {expected_size}, got {dimensions}")

    by_src = {local_path(img.get("src", "")): img for img in page.images}
    for relative in EXPECTED:
        img = by_src.get(relative)
        if not img:
            continue
        if not img.get("alt", "").strip():
            errors.append(f"missing alt text: {relative}")
        expected_w, expected_h = EXPECTED[relative]
        if img.get("width") != str(expected_w) or img.get("height") != str(expected_h):
            errors.append(f"HTML dimensions do not match file for {relative}")
        if relative in GALLERY and img.get("loading") != "lazy":
            errors.append(f"below-fold board must be lazy-loaded: {relative}")
        if relative == "assets/serotonix-mask-hero-2026.webp":
            if img.get("fetchpriority") != "high" or img.get("loading") != "eager":
                errors.append("hero image must be the only eager/high-priority SerotoniX image")
        elif img.get("fetchpriority"):
            errors.append(f"below-fold board must not set fetchpriority: {relative}")

    full_resolution = {local_path(link.get("href", "")) for link in page.links if "serotonix-" in link.get("href", "")}
    if not GALLERY.issubset(full_resolution):
        errors.append(f"missing full-resolution links: {sorted(GALLERY - full_resolution)}")

    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1
    print(f"Verified {len(EXPECTED)} SerotoniX WebP assets and {len(GALLERY)} full-resolution gallery links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
