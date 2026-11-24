#!/usr/bin/env python3
"""Test playlist streams and switch broken primaries to working alternates."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "config.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
TIMEOUT = 12
WORKERS = 8


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str | None:
    req = Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(512_000)
            return body.decode("utf-8", errors="replace")
    except Exception:
        return None


def fetch_ok(url: str, headers: dict[str, str] | None = None) -> bool:
    req = Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            # read a small chunk to confirm body is available
            resp.read(4096)
            return 200 <= getattr(resp, "status", 200) < 400
    except Exception:
        return False


def is_hls(url: str, text: str | None) -> bool:
    if text and "#EXTM3U" in text:
        return True
    return ".m3u8" in url.lower()


def check_stream(url: str, headers: dict[str, str] | None = None, *, attempts: int = 1, require_all: bool = False) -> bool:
    """Check manifest -> variant -> first segment, with optional retries.

    require_all avoids flapping: a backup must succeed on every attempt before
    it replaces a working primary.
    """
    results = []
    for _ in range(attempts):
        ok = _check_stream_once(url, headers)
        results.append(ok)
        if require_all and not ok:
            return False
        if not require_all and ok:
            return True
    return all(results)


def _check_stream_once(url: str, headers: dict[str, str] | None = None) -> bool:
    text = fetch_text(url, headers)
    if not text:
        return False
    if not is_hls(url, text):
        # Non-HLS stream: got a response body, consider it reachable.
        return len(text.strip()) > 0

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    variants = [line for line in lines if line and not line.startswith("#")]
    if not variants:
        return False

    first = urljoin(url, variants[0])
    # If first entry is already a media segment, test it directly.
    lower = first.lower()
    if ".ts" in lower or ".m4s" in lower or ".mp4" in lower:
        return fetch_ok(first, headers)

    variant_text = fetch_text(first, headers)
    if not variant_text or "#EXTM3U" not in variant_text:
        # Some streams may return media directly; try fetching as segment.
        return fetch_ok(first, headers)

    seg_lines = [line.strip() for line in variant_text.splitlines() if line.strip()]
    segments = [line for line in seg_lines if line and not line.startswith("#")]
    if not segments:
        return False
    seg_url = urljoin(first, segments[0])
    return fetch_ok(seg_url, headers)


def same_host_family(a: str, b: str) -> bool:
    ha = (urlparse(a).hostname or "").lower()
    hb = (urlparse(b).hostname or "").lower()
    if not ha or not hb:
        return False
    if ha == hb:
        return True
    # keep headers for same registered-ish suffix by last 2 labels
    return ha.split(".")[-2:] == hb.split(".")[-2:]


def pick_working(channel: dict) -> tuple[str, list[str], str] | None:
    headers = channel.get("headers") or {}
    candidates = [channel.get("url", ""), *(channel.get("alternates") or [])]
    seen = set()
    ordered = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    if not ordered:
        return None

    for i, url in enumerate(ordered):
        hdrs = headers if (not headers or same_host_family(url, ordered[0])) else {}
        # Primary: 2 tries, any success keeps it.
        # Backup: 3 consecutive successes required before replacing the primary.
        ok = check_stream(url, hdrs, attempts=2 if i == 0 else 3, require_all=i > 0)
        log(f"{'OK' if ok else 'BAD'}  {channel.get('name','?'):20} {url}")
        if ok:
            rest = [c for c in ordered if c != url]
            origin = channel.get("origin", "canlı kaynak")
            if i > 0:
                origin = "pinned"
            return url, rest[:3], origin
    return None


def main() -> int:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    data_path = os.path.join(DATA_DIR, "channels.json")
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    config_by_id = {c["id"]: c for c in config.get("channels", [])}
    changed_config = False
    changed_data = False
    results: dict[str, tuple[str, list[str], str] | None] = {}

    channels = data.get("channels", [])
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(pick_working, ch): ch for ch in channels}
        for fut in as_completed(futures):
            ch = futures[fut]
            try:
                results[ch["id"]] = fut.result()
            except Exception as e:
                log(f"HATA {ch.get('name')}: {e}")
                results[ch["id"]] = None

    for ch in channels:
        res = results.get(ch["id"])
        if res is None:
            log(f"UYARI {ch.get('name')}: çalışan alternatif bulunamadı, mevcut değer korunuyor")
            continue
        url, alternates, origin = res
        if url != ch.get("url") or alternates != ch.get("alternates", []) or origin != ch.get("origin"):
            ch["url"] = url
            ch["alternates"] = alternates
            if origin == "pinned" or ch.get("origin") in ("pinned", "fallback"):
                ch["origin"] = "pinned"
            changed_data = True

        cfg = config_by_id.get(ch["id"])
        if not cfg:
            continue
        old_pinned = cfg.get("pinned")
        old_fallback = cfg.get("fallback")
        # If the old pinned/fallback primary was broken, pin the working URL.
        if origin == "pinned" and old_pinned and old_pinned != url:
            cfg["pinned"] = url
            cfg["fallback"] = url
            changed_config = True
            # drop headers if host family changed
            if "headers" in cfg and not same_host_family(url, old_pinned):
                del cfg["headers"]
        elif origin == "pinned" and old_fallback and old_fallback != url:
            cfg["fallback"] = url
            changed_config = True
            if "headers" in cfg and not same_host_family(url, old_fallback):
                del cfg["headers"]

    if changed_config:
        with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        log("config.json güncellendi; liste yeniden üretilmeli.")
    else:
        log("Değişiklik yok.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
