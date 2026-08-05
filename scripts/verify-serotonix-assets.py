#!/usr/bin/env python3
"""Fail fast when the SerotoniX gallery contains missing, truncated or malformed assets."""
from __future__ import annotations

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from webp_integrity import inspect_webp

EXPECTED = {
    "assets/serotonix-mask-hero-2026.webp": (2200, 1524),
    "assets/serotonix-layered-architecture-2026.webp": (1536, 1024),
    "assets/serotonix-product-cad-2026.webp": (1448, 1086),
    "assets/serotonix-product-dimensions-2026.webp": (1448, 1086),
    "assets/serotonix-controller-pcba-2026.webp": (2200, 2136),
    "assets/serotonix-system-architecture-2026.webp": (1448, 1086),
    "assets/serotonix-system-control-2026.webp": (1448, 1086),
    "assets/serotonix-colour-finish-2026.webp": (1511, 2200),
}
GALLERY = set(EXPECTED) - {"assets/serotonix-mask-hero-2026.webp"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        if tag == "img":
            self.images.append(values)
        elif tag == "a":
            self.links.append(values)


def local_path(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--require-pillow",
        action="store_true",
        help="require a complete Pillow pixel decode in addition to RIFF validation",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    html_path = root / "serotonix.html"
    assets_dir = root / "assets"
    errors: list[str] = []

    if not html_path.is_file():
        print(f"ERROR: missing {html_path}", file=sys.stderr)
        return 1
    if not assets_dir.is_dir():
        print(f"ERROR: missing {assets_dir}", file=sys.stderr)
        return 1

    page = PageParser()
    page.feed(html_path.read_text(encoding="utf-8"))
    referenced = [
        local_path(item.get("src", ""))
        for item in page.images
        if "serotonix-" in item.get("src", "")
    ]

    if set(referenced) != set(EXPECTED):
        errors.append(
            f"SerotoniX image set mismatch: expected {sorted(EXPECTED)}, "
            f"found {sorted(set(referenced))}"
        )
    duplicates = sorted({item for item in referenced if referenced.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate image references: {duplicates}")

    actual_names = {path.name for path in assets_dir.iterdir() if path.is_file()}
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
            info = inspect_webp(data, require_pillow=args.require_pillow)
        except ValueError as exc:
            errors.append(f"cannot fully decode {relative}: {exc}")
            continue

        dimensions = (info.width, info.height)
        if dimensions != expected_size:
            errors.append(
                f"dimension mismatch for {relative}: expected {expected_size}, got {dimensions}"
            )

    by_src = {local_path(image.get("src", "")): image for image in page.images}
    for relative in EXPECTED:
        image = by_src.get(relative)
        if not image:
            continue
        if not image.get("alt", "").strip():
            errors.append(f"missing alt text: {relative}")

        expected_width, expected_height = EXPECTED[relative]
        if (
            image.get("width") != str(expected_width)
            or image.get("height") != str(expected_height)
        ):
            errors.append(f"HTML dimensions do not match file for {relative}")

        if relative in GALLERY and image.get("loading") != "lazy":
            errors.append(f"below-fold board must be lazy-loaded: {relative}")

        if relative == "assets/serotonix-mask-hero-2026.webp":
            if image.get("fetchpriority") != "high" or image.get("loading") != "eager":
                errors.append(
                    "hero image must be the only eager/high-priority SerotoniX image"
                )
        elif image.get("fetchpriority"):
            errors.append(f"below-fold board must not set fetchpriority: {relative}")

    full_resolution = {
        local_path(link.get("href", ""))
        for link in page.links
        if "serotonix-" in link.get("href", "")
    }
    if not GALLERY.issubset(full_resolution):
        errors.append(f"missing full-resolution links: {sorted(GALLERY - full_resolution)}")

    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    decode_mode = "RIFF and Pillow" if args.require_pillow else "RIFF"
    print(
        f"Verified {len(EXPECTED)} complete SerotoniX WebP assets "
        f"with {decode_mode} validation and {len(GALLERY)} full-resolution gallery links."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
