#!/usr/bin/env python3
"""Türk ulusal kanal listesini otomatik güncellenen kaynaklardan üretir.

Çıktılar:
  data/playlist.m3u   - M3U oynatıcılar / tvlistesi uygulaması için
  data/channels.json  - JSON API
  data/channels.js    - file:// ile açıldığında bile çalışan veri dosyası

Kullanım:
  python generate.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")

USER_AGENT = "Mozilla/5.0 (compatible; tvlistesi/1.0; +https://github.com/iptv-org/iptv)"
TIMEOUT = 25

OFFICIAL_HOSTS = (
    "medya.trt.com.tr", "live.trt.com.tr", "trt.com.tr", "ercdn.net",
    "daioncdn.net", "turkmedya", "demiroren", "ciner", "dogus",
    "kanal7", "blutv", "tele1", "tgrthaber", "yayin.com.tr",
    "mncdn.com", "mediatriple.net", "powerapp.com.tr",
)

BAD_HOSTS = (
    "vavoo", "workers.dev", "iptvperu", "playhdnew", "pishow",
    "ayakkabiparti", "cloudflarestream", "streamlock.net", "socialsmart.tv",
)


def log(message: str) -> None:
    print(message, flush=True)


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_m3u(text: str) -> list[dict]:
    """EXTINF satırlarını ve ardından gelen yayın adresini ayrıştırır."""
    entries: list[dict] = []
    info: str | None = None
    extra: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#EXTINF:"):
            info, extra = line, []
        elif line.startswith("#") and line != "#EXTM3U":
            if info is not None:
                extra.append(line)
        elif line and info is not None:
            attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', info))
            name = info.split(",", 1)[1].strip() if "," in info else ""
            lower_name = name.lower()
            resolution_match = re.search(r"\((\d{3,4})p\)", name)
            entries.append({
                "tvg_id": attrs.get("tvg-id", ""),
                "name": re.sub(r"\s*\([^)]*\)\s*", "", name).strip(),
                "url": line,
                "resolution": int(resolution_match.group(1)) if resolution_match else 0,
                "not_247": "not 24/7" in lower_name,
                "geo_blocked": "geo-blocked" in lower_name,
                "extra": extra,
            })
            info, extra = None, []

    return entries


def normalize_id(tvg_id: str) -> str:
    return tvg_id.split("@", 1)[0].strip()


def candidate_score(entry: dict) -> int:
    url = entry["url"].lower()
    host = re.sub(r"^[a-z]+://", "", url).split("/", 1)[0]
    score = 60 if url.startswith("https://") else -40

    if any(domain in host for domain in OFFICIAL_HOSTS):
        score += 80
    if any(bad in url for bad in BAD_HOSTS):
        score -= 120
    if entry["geo_blocked"]:
        score -= 140
    if entry["not_247"]:
        score -= 70

    score += entry["resolution"] // 20
    if ".m3u8" in url:
        score += 20
    if "master" in url:
        score += 10
    # Yedek adresler yalnızca canlı kaynak yoksa/bozuksa kullanılsın.
    if entry.get("is_fallback"):
        score -= 60
    return score


def build_index(entries: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    by_id: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for entry in entries:
        if entry["tvg_id"]:
            by_id.setdefault(normalize_id(entry["tvg_id"]).lower(), []).append(entry)
        by_name.setdefault(entry["name"].casefold(), []).append(entry)
    return by_id, by_name


def select_url(channel: dict, by_id: dict, by_name: dict) -> tuple[str, str, list[str]]:
    names = [channel["name"], *channel.get("aliases", [])]
    candidates: list[dict] = list(by_id.get(channel["id"].lower(), []))
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for item in candidates:
        if item["url"] not in seen_urls:
            unique.append(item)
            seen_urls.add(item["url"])
    for name in names:
        for item in by_name.get(name.casefold(), []):
            if item["url"] not in seen_urls:
                unique.append(item)
                seen_urls.add(item["url"])

    pinned = channel.get("pinned")
    if pinned:
        alternates = [item["url"] for item in unique if item["url"] != pinned][:3]
        return pinned, "pinned", alternates

    fallback = channel.get("fallback")
    if fallback:
        unique.append({
            "url": fallback, "name": channel["name"], "resolution": 1080,
            "not_247": False, "geo_blocked": False, "extra": [],
            "tvg_id": channel["id"], "is_fallback": True,
        })

    if not unique:
        return "", "yok", []

    ranked = sorted(unique, key=candidate_score, reverse=True)
    best = ranked[0]
    origin = "fallback" if best.get("is_fallback") else "canlı kaynak"
    alternates = [item["url"] for item in ranked[1:] if item["url"] != best["url"]][:3]
    return best["url"], origin, alternates


def main() -> int:
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        config = json.load(handle)

    all_entries: list[dict] = []
    working_sources: list[str] = []
    for source in config["sources"]:
        try:
            entries = parse_m3u(fetch(source))
            all_entries.extend(entries)
            working_sources.append(source)
            log(f"OK   {source} ({len(entries)} yayın)")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            log(f"UYARI  {source} alınamadı: {error}")

    if not all_entries:
        log("HATA: Kaynakların hiçbiri alınamadı; yalnızca yedek adresler kullanılacak.")

    by_id, by_name = build_index(all_entries)
    channels: list[dict] = []
    fallback_count = 0

    for channel in config["channels"]:
        url, origin, alternates = select_url(channel, by_id, by_name)
        if not url:
            continue
        if origin in ("fallback", "pinned"):
            fallback_count += 1
        logo = channel.get("logo")
        channels.append({
            "id": channel["id"],
            "name": channel["name"],
            "group": channel.get("group", "Ulusal"),
            "url": url,
            "alternates": alternates,
            "logo": f"{config['logoBase']}{logo}" if logo else "",
            "origin": origin,
        })
        if channel.get("headers"):
            channels[-1]["headers"] = channel["headers"]

    group_order = {name: index for index, name in enumerate(config.get("groups", []))}
    channels.sort(key=lambda item: (group_order.get(item["group"], 99), item["name"].casefold()))

    data = {
        "name": config["name"],
        "description": config.get("description", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": working_sources,
        "count": len(channels),
        "channels": channels,
    }

    os.makedirs(DATA_DIR, exist_ok=True)

    m3u = ["#EXTM3U"]
    for channel in channels:
        logo_attr = f' tvg-logo="{channel["logo"]}"' if channel["logo"] else ""
        m3u.append(
            f'#EXTINF:-1 tvg-id="{channel["id"]}"{logo_attr} '
            f'group-title="{channel["group"]}",{channel["name"]}'
        )
        referer = channel.get("headers", {}).get("Referer")
        if referer:
            m3u.append(f"#EXTVLCOPT:http-referrer={referer}")
        m3u.append(channel["url"])
    m3u.append("")

    with open(os.path.join(DATA_DIR, "playlist.m3u"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(m3u))

    with open(os.path.join(DATA_DIR, "channels.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    with open(os.path.join(DATA_DIR, "channels.js"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("window.TVLISTESI_DATA = ")
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write(";\n")

    log(f"Tamam: {len(channels)} kanal yazıldı ({fallback_count} sabit/yedek adres).")
    log(f"Klasör: {DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
