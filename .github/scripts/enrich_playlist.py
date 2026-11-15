import json
import re
import urllib.request
from pathlib import Path

BASE = "https://iptv-org.github.io/api/"

def get_json(name):
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "IPTV-playlist-metadata-bot"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)

def set_attr(line, key, value):
    if not value:
        return line
    escaped = str(value).replace("&", "&amp;").replace('"', "&quot;")
    pattern = re.compile(r'(?<!\S)' + re.escape(key) + r'="[^"]*"')
    replacement = key + '="' + escaped + '"'
    if pattern.search(line):
        return pattern.sub(replacement, line, count=1)
    return re.sub(r'^(#EXTINF:-?\d+(?:\.\d+)?)(\s*)', r'\1 ' + replacement + r'\2', line, count=1)

def main():
    playlist = Path("playlist.m3u")
    original = playlist.read_text(encoding="utf-8-sig")
    channels = get_json("channels.json")
    logos = get_json("logos.json")
    categories = get_json("categories.json")

    channel_by_id = {c.get("id"): c for c in channels if c.get("id")}
    category_names = {c.get("id"): c.get("name", c.get("id")) for c in categories}
    logo_by_channel = {}
    for logo in logos:
        channel_id, url = logo.get("channel"), logo.get("url")
        if not channel_id or not url:
            continue
        score = 2 if logo.get("in_use") else 1
        if channel_id not in logo_by_channel or score > logo_by_channel[channel_id][0]:
            logo_by_channel[channel_id] = (score, url)

    updated = []
    matched = logo_count = category_count = 0
    for line in original.splitlines():
        if line.startswith("#EXTINF:"):
            match = re.search(r'\btvg-id="([^"]+)"', line)
            tvg_id = match.group(1) if match else None
            channel_id = tvg_id.split("@", 1)[0] if tvg_id else None
            channel = channel_by_id.get(channel_id)
            if channel:
                matched += 1
                logo = logo_by_channel.get(channel_id)
                if logo and not re.search(r'\btvg-logo="[^"]*"', line):
                    line = set_attr(line, "tvg-logo", logo[1])
                    logo_count += 1
                names = [category_names.get(c, c) for c in (channel.get("categories") or [])]
                if names and not re.search(r'\bgroup-title="[^"]*"', line):
                    line = set_attr(line, "group-title", "; ".join(names))
                    category_count += 1
        if line.startswith("#EXTINF:"):
            country_match = re.search(r'\btvg-country="([^"]+)"', line)
            if country_match:
                country_names = {
                    "br": "Brasil", "us": "Estados Unidos", "ca": "Canadá",
                    "mx": "México", "jp": "Japão", "kr": "Coreia do Sul",
                    "pt": "Portugal", "uk": "Reino Unido", "tr": "Turquia",
                    "cn": "China", "ru": "Rússia", "es": "Espanha",
                }
                country = country_names.get(country_match.group(1), country_match.group(1))
                group_match = re.search(r'\bgroup-title="([^"]*)"', line)
                category = group_match.group(1).strip() if group_match else "Geral"
                prefix = country + " | "
                if not category.startswith(prefix):
                    category = prefix + category
                line = set_attr(line, "group-title", category)
                line = re.sub(r'\s+tvg-country="[^"]*"', "", line, count=1)
        updated.append(line)

    result = "\n".join(updated).rstrip() + "\n"
    if result != original:
        playlist.write_text(result, encoding="utf-8")
    print("Entries matched:", matched)
    print("Logos added:", logo_count)
    print("Category labels added:", category_count)
    print("Playlist changed:", result != original)

if __name__ == "__main__":
    main()
