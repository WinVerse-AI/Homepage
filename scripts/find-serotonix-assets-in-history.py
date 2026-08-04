#!/usr/bin/env python3
"""Find exact or perceptually matching supplied SerotoniX boards in every repository blob."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

SOURCES = {
    "colour": {
        "source_name": "Color&Finish 2(5).png",
        "source_sha256": "e01755a60eb6e7a0372315e112409b9cc96d436b9d6da0925960959c8fa4f6ca",
        "size": [1024, 1536],
        "dhash16": "36614de12ce031233c6795704dd0126b35678ce34dc403f032670d678cf04382",
        "ahash16": "9b3ff7ffffffdfbfcf3fffffe07fc03fc031c43fe07fe07fc03fc037c43fffff"
    },
    "layered": {
        "source_name": "Illustrative Product Layered(4).png",
        "source_sha256": "ff4243d53c38298f6238cdb64e8b62ca852e823ef698fb6fe979200a7a67d967",
        "size": [1536, 1024],
        "dhash16": "1a027dcc58e772f3331b725b761b6473696f738361f360eb31674cc74a1990c0",
        "ahash16": "0fff0ffffe73083bf98b390bb20b933fffe7b9f3b03bb023f833ff7fbfdfffff"
    },
    "pcba": {
        "source_name": "PCBA Drawings(4).png",
        "source_sha256": "2b5e523dd36c17f3194d2679b920286449191e1daa9778cd3f364d0fbcd56443",
        "size": [1536, 1024],
        "dhash16": "74207b035dac2c272d272d312c31da8e1ce914ab54ab952334a8736b53675364",
        "ahash16": "3fffffffffff001300000010863dfffffff9ffefffffffffffffffffff3fffff"
    },
    "cad": {
        "source_name": "Product CAD Drawings(6).png",
        "source_sha256": "3526042956d9d510cc618b8ed1899b59a39ce28574cf47575fc1a64c0e6babad",
        "size": [1448, 1086],
        "dhash16": "4f281ed25863c2a9a2b4c930492b38e686ce4e0d933693369b264b0d249a0044",
        "ahash16": "03ff87ff8c397014500400082481ce37f3ffe1c7cdd3c983e1a7e387f7ffffff"
    },
    "dimensions": {
        "source_name": "Product Dimensions 2(5).png",
        "source_sha256": "a2b4841603c7387a6618392aca34f11ee906ed639879ea6e556e297bf71f908e",
        "size": [1448, 1086],
        "dhash16": "6b676fa79c682c63669a569a661a25632ce398932cd66558185818d8d1a57f04",
        "ahash16": "01f183f1cf3fc73bba8b288b800f923bc77bceff865fbb0fc41fc47fffff03ff"
    },
    "control": {
        "source_name": "System Control Schematic(4).png",
        "source_sha256": "208642419937b9be56c58087c10beebff775493c977ab959a8440e460dec04c7",
        "size": [1448, 1086],
        "dhash16": "3cb778a764c969c969d9c2588cc90ce94cc99ac99ac94ce73a4509478d060e91",
        "ahash16": "1e030e0336ed04453c4dffc8e678e67fe7fd4f7d4a7fffff87e501a7e7e7ffff"
    },
    "architecture": {
        "source_name": "System Schematics(5).png",
        "source_sha256": "172dfb956b4cfa63678514c56071eea647ffabb8749a86b423a909c84e832991",
        "size": [1448, 1086],
        "dhash16": "79197b2638653365537517693465666566662661ac63265a265624570e981802",
        "ahash16": "1fff1fff9ff18135011501bd0f3131f5317ff338f7fff35ff153f3d3ffffffff"
    }
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def run(*args: str) -> bytes:
    return subprocess.check_output(args, stderr=subprocess.DEVNULL)


def hash_bits(image: Image.Image, *, difference: bool, size: int = 16) -> str:
    dimensions = (size + 1, size) if difference else (size, size)
    pixels = list(ImageOps.grayscale(image).resize(dimensions, Image.Resampling.LANCZOS).getdata())
    bits: list[bool] = []
    if difference:
        for row in range(size):
            offset = row * (size + 1)
            bits.extend(pixels[offset + column + 1] > pixels[offset + column] for column in range(size))
    else:
        mean = sum(pixels) / len(pixels)
        bits = [value > mean for value in pixels]
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
    object_lines = run("git", "rev-list", "--objects", "--all").decode("utf-8", "replace").splitlines()
    blob_paths: dict[str, set[str]] = {}
    for line in object_lines:
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        oid, path = parts
        if Path(path).suffix.lower() in IMAGE_EXTENSIONS:
            blob_paths.setdefault(oid, set()).add(path)

    decoded: list[dict[str, object]] = []
    for oid, paths in blob_paths.items():
        try:
            data = run("git", "cat-file", "blob", oid)
            digest = hashlib.sha256(data).hexdigest()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                decoded.append({
                    "blob": oid,
                    "paths": sorted(paths),
                    "bytes": len(data),
                    "sha256": digest,
                    "dimensions": list(image.size),
                    "format": image.format,
                    "dhash16": hash_bits(image, difference=True),
                    "ahash16": hash_bits(image, difference=False)
                })
        except Exception:
            continue

    report: dict[str, object] = {"scanned_decodable_blobs": len(decoded), "sources": {}}
    exact_total = 0
    for key, source in SOURCES.items():
        candidates: list[dict[str, object]] = []
        for image in decoded:
            dhash_distance = distance(str(image["dhash16"]), str(source["dhash16"]))
            ahash_distance = distance(str(image["ahash16"]), str(source["ahash16"]))
            candidate = dict(image)
            candidate.update({
                "dhash_distance": dhash_distance,
                "ahash_distance": ahash_distance,
                "combined_distance": dhash_distance + ahash_distance,
                "dimension_match": image["dimensions"] == source["size"],
                "exact_source_sha256": image["sha256"] == source["source_sha256"]
            })
            candidates.append(candidate)
        candidates.sort(key=lambda item: (
            not bool(item["exact_source_sha256"]),
            not bool(item["dimension_match"]),
            int(item["combined_distance"]),
            -int(item["bytes"])
        ))
        exact = [item for item in candidates if item["exact_source_sha256"]]
        exact_total += len(exact)
        report["sources"][key] = {"source": source, "exact_matches": exact, "top_candidates": candidates[:12]}
        print(f"\n### {key}: {source['source_name']}")
        print(f"exact matches: {len(exact)}")
        for item in candidates[:12]:
            print(json.dumps(item, sort_keys=True))

    report["exact_match_count"] = exact_total
    Path("serotonix-global-history-scan.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nScanned {len(decoded)} decodable historical image blobs; exact source matches: {exact_total}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
