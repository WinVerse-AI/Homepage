#!/usr/bin/env python3
"""Verify the deployed SerotoniX page and assets against the checked-out commit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from webp_integrity import inspect_webp

ASSETS = {
    "assets/serotonix-mask-hero-2026.webp": (2200, 1524),
    "assets/serotonix-concept-exploded-hires.webp": (2083, 2200),
    "assets/serotonix-controller-pcba-2026.webp": (2200, 2136),
    "assets/serotonix-system-schematic-hires.webp": (1633, 2200),
    "assets/serotonix-proposed-specifications-hires.webp": (2058, 2200),
    "assets/serotonix-colour-finish-2026.webp": (1511, 2200),
}


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
    separator = "&" if "?" in url else "?"
    cache_busted = f"{url}{separator}verify={time.time_ns()}"
    request = Request(
        cache_busted,
        headers={
            "User-Agent": "WinVerse-SerotoniX-Deployment-Check/2.0",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
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
    local_html = (root / "serotonix.html").read_bytes()
    local_html_sha = hashlib.sha256(local_html).hexdigest()

    report: dict[str, object] = {
        "base_url": base_url,
        "page_url": page_url,
        "commit_sha": os.environ.get("GITHUB_SHA", "local"),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "local_page_sha256": local_html_sha,
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
            live_html_sha = hashlib.sha256(html_bytes).hexdigest()
            page_ok = (
                status == 200
                and "text/html" in content_type.lower()
                and sources == set(ASSETS)
                and live_html_sha == local_html_sha
            )
            report["page"] = {
                "status": status,
                "content_type": content_type,
                "bytes": len(html_bytes),
                "sha256": live_html_sha,
                "matches_commit": live_html_sha == local_html_sha,
                "image_references": sorted(sources),
                "attempt": attempt,
                "retry_errors": page_attempts,
            }
            if page_ok:
                break
            page_attempts.append(
                f"attempt {attempt}: stale or unexpected page content "
                f"(live sha {live_html_sha}, local sha {local_html_sha})"
            )
        except Exception as exc:
            page_attempts.append(f"attempt {attempt}: {exc}")
        if attempt < args.attempts:
            time.sleep(args.delay)

    if not page_ok:
        failures.append(
            f"page did not converge to the checked-out HTML: {'; '.join(page_attempts)}"
        )

    for relative, expected_dimensions in ASSETS.items():
        local_path = root / relative
        local_bytes = local_path.read_bytes()
        local_sha = hashlib.sha256(local_bytes).hexdigest()
        item: dict[str, object] = {
            "relative_path": relative,
            "url": urljoin(base_url, relative),
            "expected_dimensions": list(expected_dimensions),
            "local_bytes": len(local_bytes),
            "local_sha256": local_sha,
        }

        try:
            local_info = inspect_webp(local_bytes, require_pillow=True)
            item.update(
                {
                    "local_declared_bytes": local_info.declared_bytes,
                    "local_chunks": list(local_info.chunks),
                    "local_dimensions": [local_info.width, local_info.height],
                    "local_full_decode": local_info.pillow_decoded,
                }
            )
            if (local_info.width, local_info.height) != expected_dimensions:
                raise ValueError(
                    f"expected dimensions {expected_dimensions}, "
                    f"decoded {(local_info.width, local_info.height)}"
                )
        except Exception as exc:
            item["local_error"] = str(exc)
            failures.append(f"{relative}: committed asset is invalid: {exc}")
            cast_assets = report["assets"]
            assert isinstance(cast_assets, list)
            cast_assets.append(item)
            continue

        asset_attempts: list[str] = []
        asset_ok = False
        for attempt in range(1, args.attempts + 1):
            try:
                status, headers, body = fetch(str(item["url"]))
                content_type = headers.get("content-type", "")
                live_sha = hashlib.sha256(body).hexdigest()
                live_info = inspect_webp(body, require_pillow=True)
                dimensions = (live_info.width, live_info.height)
                asset_ok = (
                    status == 200
                    and "image/webp" in content_type.lower()
                    and dimensions == expected_dimensions
                    and live_sha == local_sha
                )
                item.update(
                    {
                        "status": status,
                        "content_type": content_type,
                        "live_bytes": len(body),
                        "live_declared_bytes": live_info.declared_bytes,
                        "live_chunks": list(live_info.chunks),
                        "live_sha256": live_sha,
                        "dimensions": list(dimensions),
                        "full_decode": live_info.pillow_decoded,
                        "attempt": attempt,
                        "retry_errors": asset_attempts,
                        "matches_commit": live_sha == local_sha,
                    }
                )
                if asset_ok:
                    break
                asset_attempts.append(
                    f"attempt {attempt}: stale or unexpected fully decoded asset"
                )
            except Exception as exc:
                asset_attempts.append(f"attempt {attempt}: {exc}")
            if attempt < args.attempts:
                time.sleep(args.delay)

        if not asset_ok:
            item["error"] = "; ".join(asset_attempts)
            failures.append(f"{relative}: did not converge to valid committed bytes")

        cast_assets = report["assets"]
        assert isinstance(cast_assets, list)
        cast_assets.append(item)

    report["failures"] = failures
    report["passed"] = not failures
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print(
        f"Verified exact live HTML and {len(ASSETS)} fully decoded production image assets "
        f"at {base_url}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
