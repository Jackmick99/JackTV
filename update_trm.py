import os
import subprocess
from pathlib import Path

YOUTUBE_URL = "https://www.youtube.com/watch?v=wHJHpOP7vjM"
PLAYLIST = Path("playlist.m3u")

cookies = os.environ.get("YOUTUBE_COOKIES")

if not cookies:
    raise SystemExit("Secret YOUTUBE_COOKIES non trovato")

if not PLAYLIST.exists():
    raise SystemExit("playlist.m3u non trovato")

cookie_file = Path("cookies.txt")
cookie_file.write_text(cookies, encoding="utf-8")

try:
    result = subprocess.run(
        [
            "yt-dlp",
            "--no-warnings",
            "--cookies", str(cookie_file),
            "--get-url",
            "-f", "best[protocol*=m3u8]/best",
            YOUTUBE_URL,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit("Impossibile ottenere lo stream YouTube")

    urls = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("http")
    ]

    if not urls:
        raise SystemExit("Nessun URL dello stream trovato")

    stream_url = urls[-1]

    lines = PLAYLIST.read_text(encoding="utf-8").splitlines()

    trm_index = None

    for i, line in enumerate(lines):
        if line.startswith("#EXTINF:") and "TRM H24" in line:
            trm_index = i
            break

    if trm_index is None:
        raise SystemExit("Voce TRM H24 non trovata")

    # L'URL si trova dopo eventuali #EXTVLCOPT.
    url_index = None

    for i in range(trm_index + 1, min(trm_index + 5, len(lines))):
        if not lines[i].startswith("#"):
            url_index = i
            break

    if url_index is None:
        raise SystemExit("URL di TRM H24 non trovato")

    old_url = lines[url_index]

    lines[url_index] = stream_url

    # Scriviamo solo dopo aver completato tutti i controlli.
    PLAYLIST.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    print("TRM H24 aggiornato correttamente.")
    print(f"Vecchio URL: {old_url[:60]}...")
    print("Nuovo URL ottenuto da YouTube.")

finally:
    cookie_file.unlink(missing_ok=True)