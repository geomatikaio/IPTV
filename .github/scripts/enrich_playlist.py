import json
import re
import urllib.request
from pathlib import Path

BASE = "https://iptv-org.github.io/api/"
FILES = ("channels.json", "logos.json", "categories.json")

def get_json(name):
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "IPTV-playlist-metadata-bot"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)

def set_attr(line, key, value):
    if not value:
        return line
    escaped = str(value).replace("&", "&amp;").replace('"', "&quot;")
    pattern = re.compile(r'(?<!\\S)' + re.escape(key) + r'="[^"]*"')
    replacement = key + '="' + escaped + '"'
    if pattern.search(line):
        return pattern.sub(replacement, line, count=1)
    # Insert attributes immediately after EXTINF duration.
    return re.sub(r'^(#EXTINF:-?\\d+(?:\\.\\d+)?)(\\s*)', r'\\1 ' + replacement + r'\\2', line, count=1)

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
        channel_id = logo.get("channel")
        url = logo.get("url")
        if not channel_id or not url:
            continue
        # Prefer logos marked in use; otherwise retain the first valid logo.
        score = 2 if logo.get("in_use") else 1
        current = logo_by_channel.get(channel_id)
        if current is None or score > current[0]:
            logo_by_channel[channel_id] = (score, url)

    lines = original.splitlines()
    updated = []
    current_id = None
    matched = 0
    logo_count = 0
    category_count = 0

    for line in lines:
        if line.startswith("#EXTINF:"):
            match = re.search(r'\\btvg-id="([^"]+)"', line)
            current_id = match.group(1) if match else None
            channel_id = current_id.split("@", 1)[0] if current_id else None
            channel = channel_by_id.get(channel_id)
            if channel:
                matched += 1
                logo = logo_by_channel.get(channel_id)
                if logo and not re.search(r'\\btvg-logo="[^"]*"', line):
                    line = set_attr(line, "tvg-logo", logo[1])
                    logo_count += 1
                cats = channel.get("categories") or []
                names = [category_names.get(c, c) for c in cats]
                if names and not re.search(r'\\bgroup-title="[^"]*"', line):
                    line = set_attr(line, "group-title", "; ".join(names))
                    category_count += 1
        updated.append(line)

    result = "\\n".join(updated).rstrip() + "\\n"
    if result != original:
        playlist.write_text(result, encoding="utf-8")
    print("Entries matched:", matched)
    print("Logos added:", logo_count)
    print("Category labels added:", category_count)
    print("Playlist changed:", result != original)

if __name__ == "__main__":
    main()
