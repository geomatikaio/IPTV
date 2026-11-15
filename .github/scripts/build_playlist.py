import urllib.request
from pathlib import Path

COUNTRIES = ["br", "us", "ca", "mx", "jp", "kr", "pt", "uk", "tr", "cn", "ru", "es"]
BASE = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/"
COUNTRY_NAMES = {
    "br": "Brasil", "us": "Estados Unidos", "ca": "Canadá",
    "mx": "México", "jp": "Japão", "kr": "Coreia do Sul",
    "pt": "Portugal", "uk": "Reino Unido", "tr": "Turquia",
    "cn": "China", "ru": "Rússia", "es": "Espanha",
}

def add_country_group(entry, country):
    label = COUNTRY_NAMES[country]
    for index, line in enumerate(entry):
        if line.startswith("#EXTINF:"):
            match = __import__("re").search(r'\bgroup-title="([^"]*)"', line)
            category = match.group(1).strip() if match else "Geral"
            prefix = label + " | "
            if not category.startswith(prefix):
                category = prefix + category
            escaped = category.replace("&", "&amp;").replace('"', "&quot;")
            if match:
                line = line[:match.start(1)] + escaped + line[match.end(1):]
            else:
                line = __import__("re").sub(r'^(#EXTINF:-?\d+(?:\.\d+)?)(\s*)',
                                            r'\1 group-title="' + escaped + r'"\2', line, count=1)
            entry[index] = line
            break
    return entry

def fetch(country):
    request = urllib.request.Request(
        BASE + country + ".m3u",
        headers={"User-Agent": "IPTV-playlist-builder"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8-sig").splitlines()

def main():
    blocks = []
    seen = set()
    counts = {}

    for country in COUNTRIES:
        lines = fetch(country)
        current = []
        added = 0
        for line in lines:
            if line.startswith("#EXTM3U"):
                continue
            if line.startswith("#EXTINF:"):
                if current:
                    url = next((x.strip() for x in reversed(current)
                                if x.strip() and not x.lstrip().startswith("#")), "")
                    signature = (current[0], url)
                    if url and signature not in seen:
                        seen.add(signature)
                        blocks.append(add_country_group(current, country))
                        added += 1
                current = [line]
            elif current:
                current.append(line)
        if current:
            url = next((x.strip() for x in reversed(current)
                        if x.strip() and not x.lstrip().startswith("#")), "")
            signature = (current[0], url)
            if url and signature not in seen:
                seen.add(signature)
                blocks.append(add_country_group(current, country))
                added += 1
        counts[country] = added

    output = ["#EXTM3U"]
    for block in blocks:
        output.extend(block)
    Path("playlist.m3u").write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    print("Country entries:", counts)
    print("Unique playlist entries:", len(blocks))

if __name__ == "__main__":
    main()
