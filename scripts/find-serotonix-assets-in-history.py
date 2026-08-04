#!/usr/bin/env python3
"""Rank historical SerotoniX image blobs against hashes of the supplied source boards."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

SOURCES = {
    "assets/serotonix-colour-finish-2026.webp": {
        "size": [1024, 1536],
        "dhash16": "36614de12ce031233c6795704dd0126b35678ce34dc403f032670d678cf04382",
        "ahash16": "9b3ff7ffffffdfbfcf3fffffe07fc03fc031c43fe07fe07fc03fc037c43fffff",
    },
    "assets/serotonix-layered-architecture-2026.webp": {
        "size": [1536, 1024],
        "dhash16": "1a027dcc58e772f3331b725b761b6473696f738361f360eb31674cc74a1990c0",
        "ahash16": "0fff0ffffe73083bf98b390bb20b933fffe7b9f3b03bb023f833ff7fbfdfffff",
    },
    "assets/serotonix-controller-pcba-2026.webp": {
        "size": [1536, 1024],
        "dhash16": "74207b035dac2c272d272d312c31da8e1ce914ab54ab952334a8736b53675364",
        "ahash16": "3fffffffffff001300000010863dfffffff9ffefffffffffffffffffff3fffff",
    },
    "assets/serotonix-product-cad-2026.webp": {
        "size": [1448, 1086],
        "dhash16": "4f281ed25863c2a9a2b4c930492b38e686ce4e0d933693369b264b0d249a0044",
        "ahash16": "03ff87ff8c397014500400082481ce37f3ffe1c7cdd3c983e1a7e387f7ffffff",
    },
    "assets/serotonix-product-dimensions-2026.webp": {
        "size": [1448, 1086],
        "dhash16": "6b676fa79c682c63669a569a661a25632ce398932cd66558185818d8d1a57f04",
        "ahash16": "01f183f1cf3fc73bba8b288b800f923bc77bceff865fbb0fc41fc47fffff03ff",
    },
    "assets/serotonix-system-control-2026.webp": {
        "size": [1448, 1086],
        "dhash16": "3cb778a764c969c969d9c2588cc90ce94cc99ac99ac94ce73a4509478d060e91",
        "ahash16": "1e030e0336ed04453c4dffc8e678e67fe7fd4f7d4a7fffff87e501a7e7e7ffff",
    },
    "assets/serotonix-system-architecture-2026.webp": {
        "size": [1448, 1086],
        "dhash16": "79197b2638653365537517693465666566662661ac63265a265624570e981802",
        "ahash16": "1fff1fff9ff18135011501bd0f3131f5317ff338f7fff35ff153f3d3ffffffff",
    },
}


def run(*args: str) -> bytes:
    return subprocess.check_output(args)


def hash_bits(image: Image.Image, *, difference: bool, size: int = 16) -> str:
    dimensions = (size + 1, size) if difference else (size, size)
    array = list(ImageOps.grayscale(image).resize(dimensions, Image.Resampling.LANCZOS).getdata())
    bits: list[bool] = []
    if difference:
        for row in range(size):
            offset = row * (size + 1)
            bits.extend(array[offset + col + 1] > array[offset + col] for col in range(size))
    else:
        mean = sum(array) / len(array)
        bits = [value > mean for value in array]
    result = bytearray()
    for index in range(0, len(bits), 8):
        value = 0
        for bit in bits[index:index + 8]:
            value = (value << 1) | int(bit)
        result.append(value)
    return result.hex()


def distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def main() -> int:
    report: dict[str, list[dict[str, object]]] = {}
    for path, source in SOURCES.items():
        commits = run("git", "log", "--all", "--format=%H", "--", path).decode().splitlines()
        unique: dict[str, str] = {}
        for commit in commits:
            try:
                blob = run("git", "rev-parse", f"{commit}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                continue
            unique.setdefault(blob, commit)
        candidates: list[dict[str, object]] = []
        for blob, commit in unique.items():
            data = run("git", "cat-file", "blob", blob)
            item: dict[str, object] = {
                "blob": blob,
                "commit": commit,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            try:
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
                    dhash = hash_bits(image, difference=True)
                    ahash = hash_bits(image, difference=False)
                    item.update({
                        "dimensions": list(image.size),
                        "format": image.format,
                        "dhash16": dhash,
                        "ahash16": ahash,
                        "dhash_distance": distance(dhash, str(source["dhash16"])),
                        "ahash_distance": distance(ahash, str(source["ahash16"])),
                        "dimension_match": list(image.size) == source["size"],
                    })
                    item["combined_distance"] = int(item["dhash_distance"]) + int(item["ahash_distance"])
            except Exception as exc:
                item["decode_error"] = str(exc)
                item["combined_distance"] = 9999
            candidates.append(item)
        candidates.sort(key=lambda item: (int(item["combined_distance"]), -int(item["bytes"])))
        report[path] = candidates[:8]
        print(f"\n### {path}")
        for item in candidates[:8]:
            print(json.dumps(item, sort_keys=True))
    Path("serotonix-history-scan.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
