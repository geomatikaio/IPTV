import concurrent.futures
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PLAYLIST = Path("playlist.m3u")
STATE = Path("stream_health.json")
MAX_FAILURES = 3
WORKERS = 32
TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; IPTV-Health-Check/1.0)",
    "Accept": "*/*",
}

def get(url, limit=131072):
    request = urllib.request.Request(url, headers={**HEADERS, "Range": "bytes=0-131071"})
    try:
        response = urllib.request.urlopen(request, timeout=TIMEOUT)
        data = response.read(limit)
        return response.status, data
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except Exception:
        return 0, b""

def probe(url):
    status, body = get(url)
    if status in (401, 403):
        return "blocked"
    if status in (404, 410):
        return "failed"
    if status < 200 or status >= 400 or not body:
        return "failed"

    # For HLS, verify both the manifest and at least one media segment.
    if b"#EXTM3U" in body[:4096] or ".m3u8" in url.lower():
        text = body.decode("utf-8", errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        target = None
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                target = next((x for x in lines[i + 1:] if not x.startswith("#")), None)
                if target:
                    break
        if target:
            child_url = urllib.parse.urljoin(url, target)
            child_status, child_body = get(child_url)
            if child_status in (401, 403):
                return "blocked"
            if child_status < 200 or child_status >= 400 or not child_body:
                return "failed"
            body = child_body
            url = child_url
            text = body.decode("utf-8", errors="ignore")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
        segment = next((x for x in lines if not x.startswith("#") and
                        not x.lower().startswith("http") is False), None)
        if segment is None:
            segment = next((x for x in lines if not x.startswith("#")), None)
        if segment:
            segment_url = urllib.parse.urljoin(url, segment)
            seg_status, seg_body = get(segment_url, limit=2048)
            if seg_status in (401, 403):
                return "blocked"
            if seg_status < 200 or seg_status >= 400 or not seg_body:
                return "failed"
    return "ok"

def parse_entries(lines):
    entries = []
    current = []
    for line in lines:
        if line.startswith("#EXTINF:"):
            if current:
                entries.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        entries.append(current)
    return entries

def entry_url(entry):
    return next((x.strip() for x in reversed(entry)
                 if x.strip() and not x.lstrip().startswith("#")), "")

def main():
    lines = PLAYLIST.read_text(encoding="utf-8-sig").splitlines()
    header = lines[0] if lines and lines[0].startswith("#EXTM3U") else "#EXTM3U"
    entries = parse_entries(lines[1:] if lines and lines[0].startswith("#EXTM3U") else lines)

    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    urls = sorted({entry_url(e) for e in entries if entry_url(e)})
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(probe, url): url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = "failed"

    removed = set()
    new_state = {}
    ok = failed = blocked = 0
    for url, result in results.items():
        old = state.get(url, {})
        failures = int(old.get("failures", 0)) if isinstance(old, dict) else 0
        if result == "ok":
            ok += 1
            continue
        if result == "blocked":
            blocked += 1
            if failures:
                new_state[url] = {"failures": failures}
            continue
        failed += 1
        failures += 1
        if failures >= MAX_FAILURES:
            removed.add(url)
        else:
            new_state[url] = {"failures": failures}

    kept = [e for e in entries if entry_url(e) not in removed]
    output = [header]
    for entry in kept:
        output.extend(entry)
    PLAYLIST.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Unique URLs tested: {len(urls)}")
    print(f"Responding: {ok}; failed this run: {failed}; blocked/forbidden (not removed): {blocked}")
    print(f"URLs removed after {MAX_FAILURES} consecutive failures: {len(removed)}")
    print(f"Playlist entries before: {len(entries)}; after: {len(kept)}")

if __name__ == "__main__":
    main()
