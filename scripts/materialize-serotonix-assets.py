#!/usr/bin/env python3
"""Reconstruct staged SerotoniX WebP binaries, validate them and patch page metadata."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".asset-staging"
MANIFEST = ROOT / "assets/serotonix-source-manifest.json"
HTML = ROOT / "serotonix.html"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    html = HTML.read_text(encoding="utf-8")

    for item in manifest["assets"]:
        production = ROOT / item["production_path"]
        stem = production.name
        parts = sorted(STAGING.glob(f"{stem}.b64.part-*"))
        if not parts:
            raise SystemExit(f"No staged chunks found for {stem}")
        encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
        try:
            data = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise SystemExit(f"Invalid base64 for {stem}: {exc}") from exc
        actual_hash = sha256(data)
        if actual_hash != item["production_sha256"]:
            raise SystemExit(
                f"SHA-256 mismatch for {stem}: expected {item['production_sha256']}, got {actual_hash}"
            )
        if len(data) != item["bytes"]:
            raise SystemExit(f"Byte-size mismatch for {stem}: expected {item['bytes']}, got {len(data)}")
        production.write_bytes(data)
        with Image.open(production) as image:
            image.load()
            if image.format != "WEBP":
                raise SystemExit(f"Unexpected format for {stem}: {image.format}")
            if image.size != (item["width"], item["height"]):
                raise SystemExit(
                    f"Dimension mismatch for {stem}: expected {(item['width'], item['height'])}, got {image.size}"
                )

        escaped = re.escape(item["production_path"])
        token = item["production_sha256"][:12]
        pattern = re.compile(
            rf'(?P<prefix>(?:src|href)="{escaped})(?:\?v=[^"]+)?(?P<suffix>")'
        )
        html, count = pattern.subn(rf'\g<prefix>?v={token}\g<suffix>', html)
        if count != 2:
            raise SystemExit(f"Expected two HTML references for {stem}, updated {count}")

        img_pattern = re.compile(
            rf'(<img\s+src="{escaped}\?v={token}"[^>]*?)\swidth="\d+"\sheight="\d+"([^>]*>)'
        )
        html, count = img_pattern.subn(
            rf'\1 width="{item["width"]}" height="{item["height"]}"\2', html
        )
        if count != 1:
            raise SystemExit(f"Expected one image element for {stem}, updated {count}")

    HTML.write_text(html, encoding="utf-8")
    if STAGING.exists():
        shutil.rmtree(STAGING)
    temporary_workflow = ROOT / ".github/workflows/materialize-serotonix-assets.yml"
    if temporary_workflow.exists():
        temporary_workflow.unlink()
    print(f"Materialised and verified {len(manifest['assets'])} SerotoniX production assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
