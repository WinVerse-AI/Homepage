#!/usr/bin/env python3
"""Strict WebP container and decoder validation shared by deployment checks."""
from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class WebPInfo:
    width: int
    height: int
    declared_bytes: int
    chunks: tuple[str, ...]
    pillow_decoded: bool | None


def _lossy_dimensions(payload: bytes) -> tuple[int, int]:
    marker = payload.find(b"\x9d\x01\x2a", 0, min(len(payload), 64))
    if marker < 0 or marker + 7 > len(payload):
        raise ValueError("VP8 frame header not found")
    width = int.from_bytes(payload[marker + 3 : marker + 5], "little") & 0x3FFF
    height = int.from_bytes(payload[marker + 5 : marker + 7], "little") & 0x3FFF
    if width <= 0 or height <= 0:
        raise ValueError("invalid VP8 dimensions")
    return width, height


def inspect_webp(data: bytes, *, require_pillow: bool = False) -> WebPInfo:
    """Validate the full RIFF container and, when available, decode every pixel."""
    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a RIFF/WebP file")

    declared_bytes = int.from_bytes(data[4:8], "little") + 8
    if declared_bytes != len(data):
        raise ValueError(
            f"truncated or overlong RIFF container: header declares {declared_bytes} bytes, "
            f"file contains {len(data)}"
        )

    offset = 12
    chunks: list[str] = []
    dimensions: tuple[int, int] | None = None
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError(f"incomplete WebP chunk header at byte {offset}")

        fourcc_bytes = data[offset : offset + 4]
        fourcc = fourcc_bytes.decode("ascii", "replace")
        payload_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload_start = offset + 8
        payload_end = payload_start + payload_size
        padded_end = payload_end + (payload_size & 1)

        if payload_end > len(data) or padded_end > len(data):
            raise ValueError(
                f"truncated {fourcc!r} chunk: requires byte {padded_end}, file ends at {len(data)}"
            )

        payload = data[payload_start:payload_end]
        chunks.append(fourcc)

        if fourcc_bytes == b"VP8X":
            if len(payload) < 10:
                raise ValueError("short VP8X payload")
            candidate = (
                1 + int.from_bytes(payload[4:7], "little"),
                1 + int.from_bytes(payload[7:10], "little"),
            )
            dimensions = dimensions or candidate
        elif fourcc_bytes == b"VP8L":
            if len(payload) < 5 or payload[0] != 0x2F:
                raise ValueError("invalid VP8L payload")
            bits = int.from_bytes(payload[1:5], "little")
            candidate = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            dimensions = dimensions or candidate
        elif fourcc_bytes == b"VP8 ":
            dimensions = dimensions or _lossy_dimensions(payload)

        offset = padded_end

    if offset != len(data):
        raise ValueError(f"RIFF traversal stopped at {offset}, file ends at {len(data)}")
    if not chunks:
        raise ValueError("WebP contains no chunks")
    if dimensions is None:
        raise ValueError("WebP contains no decodable VP8/VP8L/VP8X dimensions")

    pillow_decoded: bool | None = None
    try:
        from PIL import Image
    except ImportError:
        if require_pillow:
            raise ValueError("Pillow is required for full WebP decoding but is not installed")
    else:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                decoded_size = image.size
                decoded_format = image.format
        except Exception as exc:
            raise ValueError(f"full WebP decode failed: {exc}") from exc
        if decoded_format != "WEBP":
            raise ValueError(f"decoder identified {decoded_format!r}, expected 'WEBP'")
        if decoded_size != dimensions:
            raise ValueError(
                f"container dimensions {dimensions} do not match decoded dimensions {decoded_size}"
            )
        pillow_decoded = True

    return WebPInfo(
        width=dimensions[0],
        height=dimensions[1],
        declared_bytes=declared_bytes,
        chunks=tuple(chunks),
        pillow_decoded=pillow_decoded,
    )
