"""Refresh only reviewed JackTV EPG associations; Python standard library only."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET

UTC = timezone.utc
MAX_DOWNLOAD = 100 * 1024 * 1024


def stamp(value):
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S %z")
    except (ValueError, TypeError):
        return None


def xml_text(value):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))


def canonical_programmes(items, now):
    """Validate timestamps, retain yesterday through 14 days, remove overlaps."""
    lower = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    upper = now + timedelta(days=14)
    valid = []
    for p in items:
        start, stop = stamp(p.get("start")), stamp(p.get("stop"))
        if (start and stop and start < stop and stop > lower and start < upper
                and p.findtext("title", "").strip()):
            valid.append((start, stop, p))
    result, end, seen = [], None, set()
    for start, stop, p in sorted(valid, key=lambda x: (x[0], -(x[1] - x[0]).total_seconds())):
        key = (start, stop, p.findtext("title"))
        if key in seen or (end is not None and start < end):
            continue
        seen.add(key)
        end = stop
        result.append(p)
    return result


def future(items, now):
    return any(stamp(p.get("stop")) > now for p in items)


def parse_xmltv(data, wanted):
    """Stream national XMLTV; keep only the requested channel IDs."""
    raw = io.BytesIO(data)
    stream = gzip.GzipFile(fileobj=raw) if data.startswith(b"\x1f\x8b") else raw
    results = defaultdict(list)
    # External entities are not fetched by ElementTree. Reject internal DTDs.
    prefix = stream.read(65536)
    if b"<!ENTITY" in prefix.upper():
        raise ValueError("XMLTV with a DTD is not accepted")
    stream.seek(0)
    iterator = ET.iterparse(stream, events=("start", "end"))
    _, root = next(iterator)
    if root.tag != "tv":
        raise ValueError("Not an XMLTV document")
    for event, element in iterator:
        if event != "end" or element.tag not in ("channel", "programme"):
            continue
        if element.tag == "programme" and element.get("channel") in wanted:
            results[element.get("channel")].append(deepcopy(element))
        element.clear()
        root.clear()
    return results


def parse_zappr(data, channels):
    payload = json.loads(data)
    results = {}
    for c in channels:
        items = payload.get(c["provider"], {})
        items = items.get(c["source_id"], []) if isinstance(items, dict) else []
        result = []
        for item in items:
            try:
                start = datetime.fromisoformat(item["startTime"]["iso"])
                stop = datetime.fromisoformat(item["endTime"]["iso"])
                title = item["name"]
                if not title or not start.tzinfo or not stop.tzinfo or stop <= start:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            p = ET.Element("programme", channel=c["id"],
                           start=start.strftime("%Y%m%d%H%M%S %z"),
                           stop=stop.strftime("%Y%m%d%H%M%S %z"))
            ET.SubElement(p, "title", lang="it").text = xml_text(title)
            for source, target in (("subtitle", "sub-title"), ("description", "desc")):
                if isinstance(item.get(source), str) and item[source]:
                    ET.SubElement(p, target, lang="it").text = xml_text(item[source])
            result.append(p)
        results[c["id"]] = result
    return results


def download(url, cache):
    key = hashlib.sha256(url.encode()).hexdigest() + ".bin"
    file = cache / key
    # Cache is scoped to this invocation (a temporary directory by default).
    if file.exists():
        return file.read_bytes()
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JackTV-EPG/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read(MAX_DOWNLOAD + 1)
            if len(data) > MAX_DOWNLOAD:
                raise ValueError("Source exceeds download size limit")
            file.write_bytes(data)
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_source(url, channels, cache):
    data = download(url, cache)
    if channels[0]["format"] == "zappr":
        return parse_zappr(data, channels)
    parsed = parse_xmltv(data, {c["source_id"] for c in channels})
    return {c["id"]: parsed.get(c["source_id"], []) for c in channels}


def fetch_reviewed_sources(channels, cache, now):
    """Try reviewed sources in order, stopping at the first valid future guide."""
    choices = {c["id"]: [c, *c.get("fallback_sources", [])] for c in channels}
    fetched, errors, selected, attempted = {}, {}, {}, defaultdict(list)
    for priority in range(max((len(s) for s in choices.values()), default=0)):
        groups = defaultdict(list)
        for c in channels:
            cid = c["id"]
            if cid in fetched or priority >= len(choices[cid]):
                continue
            source = choices[cid][priority]
            groups[(source["source_url"], source["format"])].append({**source, "id": cid})
            attempted[cid].append({key: source[key] for key in ("source_url", "source_id")})
        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks = {pool.submit(fetch_source, url, group, cache): (url, group)
                     for (url, _), group in groups.items()}
            for task in as_completed(tasks):
                url, group = tasks[task]
                try:
                    result = task.result()
                    for c in group:
                        cid = c["id"]
                        current = canonical_programmes(result.get(cid, []), now)
                        if future(current, now):
                            fetched[cid] = current
                            selected[cid] = {key: c[key] for key in ("source_url", "source_id")}
                            if priority:
                                print("FALLBACK", cid, url, flush=True)
                    print("OK", url, flush=True)
                except Exception as exc:
                    errors[url] = f"{type(exc).__name__}: {exc}"
                    print("SOURCE FAILED", url, type(exc).__name__, flush=True)
    return fetched, errors, selected, attempted


@contextmanager
def scratch_directory(parent=None):
    parent = Path(parent or tempfile.gettempdir()).resolve()
    folder = parent / ("jacktv-epg-" + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        # A generated, owned child only; never remove an arbitrary path.
        if folder.resolve().parent != parent or not folder.name.startswith("jacktv-epg-"):
            raise ValueError("Unsafe temporary directory path")
        shutil.rmtree(folder)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("xb") as f:
        f.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def assemble(channels, fetched, previous, now):
    root = ET.Element("tv", {"generator-info-name": "JackTV EPG updater"})
    report, programmes = [], []
    for c in channels:
        cid = c["id"]
        current = canonical_programmes(fetched.get(cid, []), now)
        mode = "fresh"
        if not future(current, now):
            current = canonical_programmes(previous.get(cid, []), now)
            mode = "previous" if future(current, now) else "missing"
        if mode == "missing":
            current = []
        channel = ET.SubElement(root, "channel", id=cid)
        ET.SubElement(channel, "display-name").text = c["name"]
        for p in current:
            p = deepcopy(p)
            p.set("channel", cid)
            programmes.append(p)
        report.append({"id": cid, "name": c["name"], "status": mode,
                       "programmes": len(current),
                       "until": current[-1].get("stop") if current else None})
    root.extend(programmes)
    return root, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cache-dir", type=Path, help="Reuse downloads for local verification only")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    now = datetime.now(UTC)
    root = args.root.resolve()
    output = args.output or root / "JackTV_EPG.xml.gz"
    playlist = (root / "playlist.m3u").read_text(encoding="utf-8-sig")
    ids = set(re.findall(r'tvg-id="([^\"]+)"', playlist))
    config = json.loads((root / "epg/channels.json").read_text(encoding="utf-8"))
    all_channels = config["channels"]
    if len({c["id"] for c in all_channels}) != len(all_channels):
        raise ValueError("Duplicate IDs in reviewed mapping")
    channels = [c for c in all_channels if c["id"] in ids]
    if not channels:
        raise ValueError("No reviewed channel found in playlist")
    unknown = sorted(ids - {c["id"] for c in channels})
    previous = {}
    old_file = root / "JackTV_EPG.xml.gz"
    if old_file.exists():
        previous = parse_xmltv(old_file.read_bytes(), ids)
    with (nullcontext(args.cache_dir) if args.cache_dir else scratch_directory()) as temporary:
        cache = args.cache_dir or Path(temporary)
        cache.mkdir(parents=True, exist_ok=True)
        fetched, errors, selected, attempted = fetch_reviewed_sources(channels, cache, now)
    xml, report = assemble(channels, fetched, previous, now)
    for c in report:
        c["source_used"] = selected.get(c["id"])
        c["sources_attempted"] = attempted[c["id"]]
    fresh = sum(c["status"] == "fresh" for c in report)
    missing = sum(c["status"] == "missing" for c in report)
    fallback = sum(c["status"] == "previous" for c in report)
    accepted = fresh >= len(channels) * .90 and missing <= len(channels) * .05
    status = {"checked_at": now.isoformat(), "accepted": accepted,
              "channels": len(channels), "fresh": fresh, "previous": fallback,
              "missing": missing, "unknown_playlist_ids": unknown,
              "source_errors": errors, "coverage": report}
    # Diagnostic files are retained as CI artifacts even if validation fails.
    diagnostic = root / "epg/last-attempt.json"
    atomic_write(diagnostic, (json.dumps(status, ensure_ascii=False, indent=2) + "\n").encode())
    summary = (f"## JackTV EPG\n\nGuide: {len(channels)}; nuove: {fresh}; "
               f"recuperate dalla guida precedente: {fallback}; mancanti: {missing}.\n\n"
               f"ID nuovi da verificare: {len(unknown)}. Fonti non disponibili: {len(errors)}.\n\n"
               + ("Verifiche superate.\n" if accepted else "Aggiornamento bloccato: guida pubblicata conservata.\n"))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary)
    print(summary)
    if not accepted:
        print(f"EPG mancanti ({missing}):", flush=True)
        for c in report:
            if c["status"] == "missing":
                sources = "; ".join(f"{s['source_url']} (ID fonte: {s['source_id']})"
                                    for s in c["sources_attempted"])
                print(f"- {c['name']} [{c['id']}] - fonti EPG provate: {sources}",
                      flush=True)
        raise RuntimeError("Coverage guard failed; published guide was not replaced")
    data = ET.tostring(xml, encoding="utf-8", xml_declaration=True)
    parsed = ET.fromstring(data)
    assert {c.get("id") for c in parsed.findall("channel")} == {c["id"] for c in channels}
    assert all(p.get("channel") in ids for p in parsed.findall("programme"))
    atomic_write(output, gzip.compress(data, compresslevel=9, mtime=0))
    atomic_write(root / "epg/status.json", (json.dumps(status, ensure_ascii=False, indent=2) + "\n").encode())
    print("Saved", output, "programmes:", len(parsed.findall("programme")))


if __name__ == "__main__":
    main()
